import ggwave
instance = ggwave.init()
# check how many bytes can I pack into a single packet
a=ggwave.encode("a"*1000)
result = ggwave.decode(instance, a)
ggwave.free(instance)
print(len(result))  # wow, 140 bytes! I thaught it was 64 bytes