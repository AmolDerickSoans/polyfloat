import kalshi_python
import inspect

c = kalshi_python.Configuration()
print("Has connection_timeout?", hasattr(c, "connection_timeout")) # specific to some generators
print("Has connect_timeout?", hasattr(c, "connect_timeout")) 
print("Has read_timeout?", hasattr(c, "read_timeout"))
print("Has timeout?", hasattr(c, "timeout"))
print(dir(c))
