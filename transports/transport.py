from socket import inet_ntoa
class Transport():

  def __init__(self, mode, applications, own_ip):
    # key: connection identification for {UDP,TCP}/IP: (src, sport)
    # data: connection details Connection object
    self.connections = {}
    self.mode = mode
    self.applications = applications 
    self.own_ip = own_ip
    # Template for new connections
    self.connection = None
    # Template for new handlers
    self.handler = None

  def items(self):
    return self.connections
   
  # TODO src UND dst koennen beide != own_ip (BCast) sein
  def newconnection(self, src, dst):
    """ conntype: connection template class for data handling
    src: client tuple (ip, port)
    dst: server tuple(ip, port) """
    # 0.0.0.0: UDP case where dst cannot - yet - be determined in full/half
    # mode due to python restrictions. see sparringserver.py for gory details
    if src[0] == self.own_ip or dst[0] == '0.0.0.0':
      self.connections[src] = self.connection(self, src, dst) 
      return self.connections[src]
    else:
      self.connections[dst] = self.connection(self, dst, src) 
      return self.connections[dst]

  def newhandler(self, conn, sock):
    return self.handler(conn, sock, map=None)

  def classify(self, connection):
    for application in self.applications:
      if application.classify(connection):
        connection.module = application
        return True
    return False

  def handle(self, pkt):
    if self.mode == 'TRANSPARENT':
      return self.handle_transparent(pkt)
    if self.mode == 'HALF':
      return self.handle_half(pkt)
    if self.mode == 'FULL':
      return self.handle_full(pkt)
