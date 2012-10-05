from stats import Stats
import urlparse
import webob, cStringIO, re
from socket import inet_ntoa, inet_aton
from os import SEEK_CUR, SEEK_END, SEEK_SET
from misc import ltruncate
#from pudb import set_trace; set_trace()

def init(mode):
  return Http(mode)

class Httpstats(Stats):

  def addserver(self, server, proxy = None):
    if server in self.cats['Server']:
      return
    self.cats['Server'][server] = [ proxy ]

  def setproxy(self, server, proxy): 
    self.addserver(server)
    self.cats['Server'][server][0] = proxy

  def addget(self, server, uri):
    self.addserver(server)
    self.cats['Server'][server] += [ ('GET ' + uri, None) ]
  
  def addpost(self, server, uri, file=None, original=None):
    self.addserver(server)
    if not 'Files' in self.cats:
      self.cats['Files'] = []
    if file:
      self.cats['Files'] += [file + ' original: ' + original ]
    self.cats['Server'][server] += [ ('POST ' + uri, None) ] 

  def addresponse(self, server, status):
    if server in self.cats['Server']:
      req = self.cats['Server'][server].pop()
      # TODO noch nicht ganz
      self.cats['Server'][server].append((req[0], status))

class Http():
  stats = Httpstats()

  def __init__(self, mode):
    # one of TRANSPARENT, FULL, HALF
    self.mode = mode

  def protocols(self):
    return ['http']

  def classify(self, conn):
    try:
      conn.outgoing.reset()
      out = conn.outgoing.readline()
      conn.outgoing.seek(0, SEEK_END)
      conn.incoming.reset()
      inc = conn.incoming.readline()
      conn.incoming.seek(0, SEEK_END)
      if inc.startswith('HTTP/') or out[-10:][:5] == 'HTTP/':
        self.setup(conn)
        return True
    except Exception,e:
      #print e
      return False

  def get_stats(self):
    print self.stats
    #for server, details in self.servers.items():
    #  print "%15.15s:%-4d    via PROXY: %r" % (inet_ntoa(server[0]), server[1], details)

  def log_request(self, http, conn):
    # be careful to count the connection for http://server,
    # not the proxy server (conn.remote)!
    # TODO ACHTUNG es kann zu einem Proxy/Server immer mehrere Verbindungen
    # durch unterschiedliche (lokale) Ports geben, diese koennen auch
    # ueberlappen, ist das in den Statistiken ein Problem?
    server = conn.proxy if conn.proxy else conn.remote

    # CONNECT method or transparent proxy used
    if http.method == 'CONNECT' or \
        (http.method == 'GET' and self.httpuri(http.path)):
      conn.proxy = server
      self.stats.setproxy(self.uri2serverport(http.path), conn.proxy)

    if http.method == 'GET':
      self.stats.addget(conn.remote, http.url)

    if http.method == 'POST':
      try:
        filename = None
        for k, v in http.POST.items():
          #print k
          try:
            if v.filename:
              import shutil, tempfile
              w = tempfile.NamedTemporaryFile(dir='/tmp', delete = False)
              #w = open('/tmp/xxx', 'wb')
              shutil.copyfileobj(v.file, w)
              w.close()
              filename = v.filename
              self.stats.addpost(conn.remote, http.url + " %s=%s %s" % (k, v.filename, w.name), w.name, filename)
          except Exception,e:
            self.stats.addpost(conn.remote, http.url + " %s=%s" % (k, v))
      except Exception,e:
        # stuff the query back into the send buffer
        conn.outgoing = qry + conn.outgoing
        print "-----%s\n>>>\n%s<<<" % (e, conn.outgoing.getvalue())

  def log_response(self, http, conn):
    if http.content_type != 'text/html':
      pass
    else:
      pass

    if http.status_int == 301:
      self.stats.addresponse(conn.remote, http.status + " " + http.headers['location'])
    else:
      self.stats.addresponse(conn.remote, http.status)

  def more_incoming_needed(self, conn):
    pos = conn.incoming.tell()
    conn.incoming.reset()
    # TODO _after_ the header was sent (i.e. split[1] is not empty below)
    # and no content-length was found suppress parsing until the connection
    # gets closed [ ignores HTTP pipelining as only one body's length can be
    # stored in the dictionary ]
    if not 'length' in conn.in_extra:
      while True:
        val = conn.incoming.readline()
        if 'content-length: ' in val.lower():
          conn.in_extra['length'] = int(val.split(':')[1])
          break
        # response fully red or end of headers
        if not val or val == '\r\n':
          break

    # skip parsing if body was not fully sent
    conn.incoming.seek(0, SEEK_END)
    length = conn.incoming.tell()
    conn.incoming.seek(pos)
    if 'length' in conn.in_extra and length < conn.in_extra['length']:
      return True
    return False

  def create_request(self, outgoing):
    request = webob.Request.from_bytes(outgoing) 
    # take care to cut off the dangling \r\n
    size = len(request.as_string())+2
    # take %-encoded URIs into account that got encoded by webob
    size += len(re.findall('%[0-9A-Fa-f]{2}', request.url))*2

    return (request, size)

  def create_response(self, incoming):
    h = cStringIO.StringIO(incoming)
    # webob does not want the HTTP/x.y -part of the response header
    h.seek(9)
    http = webob.Response.from_file(h)
    h.close()

    # HTTP/1.1 123 McCain\r\n
    size = 9+len(http.status)+2
    for x in http.headerlist:
          # x[0]: x[1]\r\n
          size += len(x[0])+2+len(x[1])+2
    # '\r\n'
    size += 2
    size += len(http.body)
    return (http, size)

  def setup(self, conn):
    conn.in_extra = {}
    if self.mode == 'TRANSPARENT':
      pass
    elif self.mode == 'HALF':
      conn.in_extra['buffer'] = ""
      # close this connection
      conn.in_extra['close'] = False
    elif self.mode == 'FULL':
      conn.in_extra['buffer'] = ""
      # close this connection
      conn.in_extra['close'] = False

  def handle(self, conn):
    if self.mode == 'TRANSPARENT':
      self.handle_transparent(conn)
    if self.mode == 'HALF':
      self.handle_half(conn)
    if self.mode == 'FULL':
      self.handle_full(conn)

  def handle_transparent(self, conn):
    request = None
    response = None

    # TODO gets called even if there is no new outgoing data but new incoming
    # data. this *is* a performance issue -> tcp.py!
    out = conn.outgoing.getvalue()
    while out:
      try:
        request, size = self.create_request(out)
        # TODO FIXME REMOVE
        size = len(out)
        conn.outgoing = ltruncate(conn.outgoing, size)
        # exact size of request is not 100% reliably detected
        # TODO FIXME tailor to cStringIO object / fix size calculation
        #conn.outgoing = conn.outgoing.lstrip('\n\r')
        self.log_request(request, conn)
        # TODO REENABLE
        # vs out = conn.outgoing.getvalue()
        out = out[size:]
        #print "%d byte left in out to parse" % len(out)
      except Exception,e: 
        #print e
        #print "--------------------------"
        #pprint(conn.outgoing.getvalue())
        break

    if self.more_incoming_needed(conn):
      return (request, response)

    inc = conn.incoming.getvalue()

    while inc:

      # schneidet sofort ab weil webob.Response() keine Exception bei zu kurzem Header wirft
      # TODO webob.from_file() braucht content-length-Header fuer korrektes Parsing.
      try:
        response, size = self.create_response(inc)
        # TODO FIXME REMOVE
        size = len(inc)
        conn.incoming = ltruncate(conn.incoming, size)
        #conn.incoming = conn.incoming.lstrip('\n\r')
        self.log_response(response, conn)
        inc = inc[size:]
        # parsing succeeded, clear Content-Length of http-header
        try:
          del conn.in_extra['length']
        except:
          pass
      except Exception, e: 
        #print e
        #print str(e) + "\nconn.incoming:----------------------\n" + conn.incoming
        #pprint(conn.incoming.getvalue())
        break
    return (request, response)

  def handle_half(self, conn):
    request, response = self.handle_transparent(conn)
    assert(not response)
    if request:
      request.server_name = inet_ntoa(conn.remote[0])
      request.server_port = conn.remote[1]
      response = request.get_response()
      #print "forwarded: %s" % request.url
      # TODO insert RULER and MODIFIER here
      self.log_response(response, conn)
      conn.in_extra['buffer'] = 'HTTP/1.1 ' + str(response)
      conn.in_extra['close'] = True

  def handle_full(self, conn):
    request, response = self.handle_transparent(conn)
    if request:
      conn.in_extra['buffer'] = 'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 14\r\n\r\n<h1>hola!</h1>'
      conn.in_extra['close'] = True

  def decode_body(self, http):
    if http.content_encoding == 'gzip':
      return self.fast_unzip(http.body)  
    if http.content_encoding == 'identity':
      return http.body
    if http.content_encoding == 'bzip2':
      return self.fast_unbzip(http.body)  
    if http.content_encoding == 'deflate':
      return self.fast_deflate(http.body)  
      
  def get_encoding(self, headers):
    # TODO
    """ return enconding of given headers dictionary.
    Does not handle nested encodings yet """
    for header, value in headers.items(): 
      if header.lower() == 'content-encoding':
        return value.lower()        

  def fast_deflate(self, comp):
    try:
      import zlib
      return zlib.decompress(comp)
    except:
      print "no zlib payload"

  def fast_unbzip(self, comp):
    try:
      import bz2
      return bz2.decompress(comp)
    except:
      print "no bz2 payload"

  def fast_unzip(self, comp):
    # TODO was passiert bei exception und return dec?
    try:
      import gzip
      handle = cStringIO.StringIO(comp)
      gzip_handle = gzip.GzipFile(fileobj=handle)
      dec = gzip_handle.read()
      gzip_handle.close()
    except IOError:
      print "no gzip payload"          
    return dec

  def uri2serverport(self, uri):
    u = urlparse.urlparse(uri)
    server = u.hostname
    port = u.port
    if not real_port:
      port = 80 if u.scheme == 'http' else 443 
    return (server, port)

  def httpuri(self, uri):
    return uri.startswith('http://') or uri.startswith('https://')

