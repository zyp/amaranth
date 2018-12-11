from nmigen.fhdl import *
from nmigen.back import rtlil, verilog


class ClockDivisor:
    def __init__(self, factor):
        self.v = Signal(factor, reset=2**factor-1)
        self.o = Signal()

    def get_fragment(self, platform):
        f = Module()
        f.sync += self.v.eq(self.v + 1)
        f.comb += self.o.eq(self.v[-1])
        return f.lower(platform)


sys  = ClockDomain()
ctr  = ClockDivisor(factor=16)
frag = ctr.get_fragment(platform=None)
# print(rtlil.convert(frag, ports=[sys.clk, ctr.o], clock_domains={"sys": sys}))
print(verilog.convert(frag, ports=[sys.clk, ctr.o], clock_domains={"sys": sys}))
