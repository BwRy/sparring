import dnslib
from dnslib import QTYPE
from stats import Stats

def init(mode):
  return Dns(mode)

class Dnsstats(Stats):
  dummy = None
  def addquery(self, server, q):
    self.addserver(server)
    self.cats['Server'][server] += [ 'Q: ' + str(q) ] 
  def addresponse(self, server, a):
    self.addserver(server)
    self.cats['Server'][server] += [ 'A: ', a ] 

class Dns():
  servers = {}

  def __init__(self, mode):
    # one of TRANSPARENT, FULL, HALF
    self.mode = mode
    self.stats = Dnsstats()
    #print '%s initialisiert [%s]' % (__name__,self.mode)

  def protocols(self):
    return ['dns']

  def classify(self, conn):
    ret = False

    # will throw exception if data is not assigned to another variable *SIGH*
    if conn.outgoing:
      dns = conn.outgoing.getvalue()
      try:
        question = dnslib.DNSRecord.parse(dns)
        ret = True
      except:
        pass

    if conn.incoming and not ret:
      dns = conn.incoming.getvalue()
      try:
        answer = dnslib.DNSRecord.parse(conn.incoming)
        ret = True
      except:
        pass

    return ret

  def get_stats(self):
    print self.stats

  def handle(self, conn):
    if self.mode == 'TRANSPARENT':
      return self.handle_transparent(conn)
    if self.mode == 'HALF':
      return self.handle_half(conn)
    if self.mode == 'FULL':
      return self.handle_full(conn)

  def handle_transparent(self, conn):
    while conn.outgoing:
      try:
        dns = conn.outgoing.getvalue()
        conn.outgoing.truncate(0)
        question = dnslib.DNSRecord.parse(dns)
        self.stats.addquery(conn.remote, question.get_q())
        conn.outgoing = '' # TODO nicht zuviel abschneiden ~> nur Groesse der Antwort/Frage
        ret = True
      except Exception, e:
        print 'xx',e
        pass

    while conn.incoming:
      try:
        dns = conn.incoming.getvalue()
        conn.incoming.truncate(0)
        answer = dnslib.DNSRecord.parse(dns)
        rlist = []
        for x in answer.rr:
          rlist.append(QTYPE.lookup(x.rtype) + " " + str(x.rname) + " " + str(x.rdata))
        self.stats.addresponse(conn.remote, rlist)
        conn.incoming = '' # TODO nicht zuviel abschneiden ~> nur Groesse der Antwort/Frage
        ret = True
      except Exception, e:
        print 'yy',e
        pass
        break

    while conn.incoming:
        break

  def handle_half(self, conn):
    # general outline:
    # receive request
    # spawn new request, send
    # receive answer
    # pass result
    pass

  def handle_full(self, conn):
    # receive request
    # spawn new artifical result
    # pass result
    self.handle_transparent(conn)
    pass

