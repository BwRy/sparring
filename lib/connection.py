from Queue import Queue
import cStringIO

class Connection():
  def __init__(self, transport, (l, lport), (r, rport), module = None):
    self.transport = transport
    self.module = module
    self.outgoing = cStringIO.StringIO()
    self.outqueue = Queue()
    self.incoming = cStringIO.StringIO()
    self.inqueue = Queue()
    self.local = (l, lport)
    self.remote = (r, rport)
    self.proxy = None
    self.in_extra = None # Optional information assigned by self.module routines
    self.out_extra = None # Optional information assigned by self.module routines

  def put_in(self, t):
    """ add new data to the buffer """
    self.incoming.write(t)

  def put_out(self, t):
    """ add new data to the buffer """
    self.outgoing.write(t)

  def handle(self):
    if self.module:
      self.module.handle(self)

  def classify(self):
    """ Does nothing if module is already set
    i.e. if this connection has been classified before
    """
    if self.module:
      return True
    if self.transport:
      return self.transport.classify(self)
    return False
