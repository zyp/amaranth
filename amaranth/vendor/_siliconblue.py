# Currently owned by Lattice, originally designed and built by a startup called SiliconBlue, which
# was acquired by Lattice. The primitives are prefixed with `SB_` for that reason.

from abc import abstractmethod

from ..hdl import *
from ..hdl._ir import RequirePosedge
from ..lib.cdc import ResetSynchronizer
from ..lib import io
from ..build import *


class SiliconBluePlatform(TemplatedPlatform):
    """
    .. rubric:: IceStorm toolchain

    Required tools:
        * ``yosys``
        * ``nextpnr-ice40``
        * ``icepack``

    The environment is populated by running the script specified in the environment variable
    ``AMARANTH_ENV_ICESTORM``, if present.

    Available overrides:
        * ``verbose``: enables logging of informational messages to standard error.
        * ``read_verilog_opts``: adds options for ``read_verilog`` Yosys command.
        * ``synth_opts``: adds options for ``synth_ice40`` Yosys command.
        * ``script_after_read``: inserts commands after ``read_ilang`` in Yosys script.
        * ``script_after_synth``: inserts commands after ``synth_ice40`` in Yosys script.
        * ``yosys_opts``: adds extra options for ``yosys``.
        * ``nextpnr_opts``: adds extra options for ``nextpnr-ice40``.
        * ``add_pre_pack``: inserts commands at the end in pre-pack Python script.
        * ``add_constraints``: inserts commands at the end in the PCF file.

    Build products:
        * ``{{name}}.rpt``: Yosys log.
        * ``{{name}}.json``: synthesized RTL.
        * ``{{name}}.tim``: nextpnr log.
        * ``{{name}}.asc``: ASCII bitstream.
        * ``{{name}}.bin``: binary bitstream.

    .. rubric:: iCECube2 toolchain

    This toolchain comes in two variants: ``LSE-iCECube2`` and ``Synplify-iCECube2``.

    Required tools:
        * iCECube2 toolchain
        * ``tclsh``

    The environment is populated by setting the necessary environment variables based on
    ``AMARANTH_ENV_ICECUBE2``, which must point to the root of the iCECube2 installation, and
    is required.

    Available overrides:
        * ``verbose``: enables logging of informational messages to standard error.
        * ``lse_opts``: adds options for LSE.
        * ``script_after_add``: inserts commands after ``add_file`` in Synplify Tcl script.
        * ``script_after_options``: inserts commands after ``set_option`` in Synplify Tcl script.
        * ``add_constraints``: inserts commands in SDC file.
        * ``script_after_flow``: inserts commands after ``run_sbt_backend_auto`` in SBT
          Tcl script.

    Build products:
        * ``{{name}}_lse.log`` (LSE) or ``{{name}}_design/{{name}}.htm`` (Synplify): synthesis log.
        * ``sbt/outputs/router/{{name}}_timing.rpt``: timing report.
        * ``{{name}}.edf``: EDIF netlist.
        * ``{{name}}.bin``: binary bitstream.
    """

    toolchain = None # selected when creating platform

    device  = property(abstractmethod(lambda: None))
    package = property(abstractmethod(lambda: None))

    # IceStorm templates

    _nextpnr_device_options = {
        "iCE40LP384": "--lp384",
        "iCE40LP1K":  "--lp1k",
        "iCE40LP4K":  "--lp8k",
        "iCE40LP8K":  "--lp8k",
        "iCE40HX1K":  "--hx1k",
        "iCE40HX4K":  "--hx8k",
        "iCE40HX8K":  "--hx8k",
        "iCE40UP5K":  "--up5k",
        "iCE40UP3K":  "--up5k",
        "iCE5LP4K":   "--u4k",
        "iCE5LP2K":   "--u4k",
        "iCE5LP1K":   "--u4k",
    }
    _nextpnr_package_options = {
        "iCE40LP4K":  ":4k",
        "iCE40HX4K":  ":4k",
        "iCE40UP3K":  "",
        "iCE5LP2K":   "",
        "iCE5LP1K":   "",
    }

    _icestorm_required_tools = [
        "yosys",
        "nextpnr-ice40",
        "icepack",
    ]
    _icestorm_file_templates = {
        **TemplatedPlatform.build_script_templates,
        "{{name}}.il": r"""
            # {{autogenerated}}
            {{emit_rtlil()}}
        """,
        "{{name}}.debug.v": r"""
            /* {{autogenerated}} */
            {{emit_debug_verilog()}}
        """,
        "{{name}}.ys": r"""
            # {{autogenerated}}
            {% for file in platform.iter_files(".v") -%}
                read_verilog {{get_override("read_verilog_opts")|options}} {{file}}
            {% endfor %}
            {% for file in platform.iter_files(".sv") -%}
                read_verilog -sv {{get_override("read_verilog_opts")|options}} {{file}}
            {% endfor %}
            {% for file in platform.iter_files(".il") -%}
                read_ilang {{file}}
            {% endfor %}
            read_ilang {{name}}.il
            {{get_override("script_after_read")|default("# (script_after_read placeholder)")}}
            synth_ice40 {{get_override("synth_opts")|options}} -top {{name}}
            {{get_override("script_after_synth")|default("# (script_after_synth placeholder)")}}
            write_json {{name}}.json
        """,
        "{{name}}.pcf": r"""
            # {{autogenerated}}
            {% for port_name, pin_name, attrs in platform.iter_port_constraints_bits() -%}
                set_io {{port_name}} {{pin_name}}
            {% endfor %}
            {% for signal, frequency in platform.iter_signal_clock_constraints() -%}
                set_frequency {{signal|hierarchy(".")}} {{frequency/1000000}}
            {% endfor %}
            {% for port, frequency in platform.iter_port_clock_constraints() -%}
                set_frequency {{port.name}} {{frequency/1000000}}
            {% endfor %}
            {{get_override("add_constraints")|default("# (add_constraints placeholder)")}}
        """,
    }
    _icestorm_command_templates = [
        r"""
        {{invoke_tool("yosys")}}
            {{quiet("-q")}}
            {{get_override("yosys_opts")|options}}
            -l {{name}}.rpt
            {{name}}.ys
        """,
        r"""
        {{invoke_tool("nextpnr-ice40")}}
            {{quiet("--quiet")}}
            {{get_override("nextpnr_opts")|options}}
            --log {{name}}.tim
            {{platform._nextpnr_device_options[platform.device]}}
            --package
                {{platform.package|lower}}{{platform._nextpnr_package_options[platform.device]|
                                            default("")}}
            --json {{name}}.json
            --pcf {{name}}.pcf
            --asc {{name}}.asc
        """,
        r"""
        {{invoke_tool("icepack")}}
            {{verbose("-v")}}
            {{get_override("icepack_opts")|options}}
            {{name}}.asc
            {{name}}.bin
        """
    ]

    # iCECube2 templates

    _icecube2_required_tools = [
        "synthesis",
        "synpwrap",
        "tclsh",
    ]
    _icecube2_file_templates = {
        **TemplatedPlatform.build_script_templates,
        "build_{{name}}.sh": r"""
            #!/bin/sh
            # {{autogenerated}}
            set -e{{verbose("x")}}
            # LSE environment
            export LD_LIBRARY_PATH=${{platform._toolchain_env_var}}/LSE/bin/lin64:$LD_LIBRARY_PATH
            export PATH=${{platform._toolchain_env_var}}/LSE/bin/lin64:$PATH
            export FOUNDRY=${{platform._toolchain_env_var}}/LSE
            # Synplify environment
            export LD_LIBRARY_PATH=${{platform._toolchain_env_var}}/sbt_backend/bin/linux/opt/synpwrap:$LD_LIBRARY_PATH
            export PATH=${{platform._toolchain_env_var}}/sbt_backend/bin/linux/opt/synpwrap:$PATH
            export SYNPLIFY_PATH=${{platform._toolchain_env_var}}/synpbase
            # Common environment
            export SBT_DIR=${{platform._toolchain_env_var}}/sbt_backend
            {{emit_commands("sh")}}
        """,
        "{{name}}.v": r"""
            /* {{autogenerated}} */
            {{emit_verilog()}}
        """,
        "{{name}}.debug.v": r"""
            /* {{autogenerated}} */
            {{emit_debug_verilog()}}
        """,
        "{{name}}_lse.prj": r"""
            # {{autogenerated}}
            -a SBT{{platform.family}}
            -d {{platform.device}}
            -t {{platform.package}}
            {{get_override("lse_opts")|options|default("# (lse_opts placeholder)")}}
            {% for file in platform.iter_files(".v") -%}
                -ver {{file}}
            {% endfor %}
            -ver {{name}}.v
            -sdc {{name}}.sdc
            -top {{name}}
            -output_edif {{name}}.edf
            -logfile {{name}}_lse.log
        """,
        "{{name}}_syn.prj": r"""
            # {{autogenerated}}
            {% for file in platform.iter_files(".v", ".sv", ".vhd", ".vhdl") -%}
                add_file -verilog {{file|tcl_quote}}
            {% endfor %}
            add_file -verilog {{name}}.v
            add_file -constraint {{name}}.sdc
            {{get_override("script_after_add")|default("# (script_after_add placeholder)")}}
            impl -add {{name}}_design -type fpga
            set_option -technology SBT{{platform.family}}
            set_option -part {{platform.device}}
            set_option -package {{platform.package}}
            {{get_override("script_after_options")|default("# (script_after_options placeholder)")}}
            project -result_format edif
            project -result_file {{name}}.edf
            impl -active {{name}}_design
            project -run compile
            project -run map
            project -run fpga_mapper
            file copy -force -- {{name}}_design/{{name}}.edf {{name}}.edf
        """,
        "{{name}}.sdc": r"""
            # {{autogenerated}}
            set_hierarchy_separator {/}
            {% for signal, frequency in platform.iter_signal_clock_constraints() -%}
                create_clock -name {{signal.name|tcl_quote}} -period {{1000000000/frequency}} [get_nets {{signal|hierarchy("/")|tcl_quote}}]
            {% endfor %}
            {% for port, frequency in platform.iter_port_clock_constraints() -%}
                create_clock -name {{port.name|tcl_quote}} -period {{1000000000/frequency}} [get_ports {{port.name|tcl_quote}}]
            {% endfor %}
            {{get_override("add_constraints")|default("# (add_constraints placeholder)")}}
        """,
        "{{name}}.tcl": r"""
            # {{autogenerated}}
            set device {{platform.device}}-{{platform.package}}
            set top_module {{name}}
            set proj_dir .
            set output_dir .
            set edif_file {{name}}
            set tool_options ":edifparser -y {{name}}.pcf"
            set sbt_root $::env(SBT_DIR)
            append sbt_tcl $sbt_root "/tcl/sbt_backend_synpl.tcl"
            source $sbt_tcl
            run_sbt_backend_auto $device $top_module $proj_dir $output_dir $tool_options $edif_file
            {{get_override("script_after_file")|default("# (script_after_file placeholder)")}}
            file copy -force -- sbt/outputs/bitmap/{{name}}_bitmap.bin {{name}}.bin
            exit
        """,
        "{{name}}.pcf": r"""
            # {{autogenerated}}
            {% for port_name, pin_name, attrs in platform.iter_port_constraints_bits() -%}
                set_io {{port_name}} {{pin_name}}
            {% endfor %}
        """,
    }
    _lse_icecube2_command_templates = [
        r"""synthesis -f {{name}}_lse.prj""",
        r"""tclsh {{name}}.tcl""",
    ]
    _synplify_icecube2_command_templates = [
        r"""synpwrap -prj {{name}}_syn.prj -log {{name}}_syn.log""",
        r"""tclsh {{name}}.tcl""",
    ]

    # Common logic

    def __init__(self, *, toolchain="IceStorm"):
        super().__init__()

        assert toolchain in ("IceStorm", "LSE-iCECube2", "Synplify-iCECube2")
        self.toolchain = toolchain

    @property
    def family(self):
        if self.device.startswith("iCE40"):
            return "iCE40"
        if self.device.startswith("iCE5"):
            return "iCE5"
        assert False

    @property
    def _toolchain_env_var(self):
        if self.toolchain == "IceStorm":
            return f"AMARANTH_ENV_{self.toolchain}"
        if self.toolchain in ("LSE-iCECube2", "Synplify-iCECube2"):
            return f"AMARANTH_ENV_ICECUBE2"
        assert False

    @property
    def required_tools(self):
        if self.toolchain == "IceStorm":
            return self._icestorm_required_tools
        if self.toolchain in ("LSE-iCECube2", "Synplify-iCECube2"):
            return self._icecube2_required_tools
        assert False

    @property
    def file_templates(self):
        if self.toolchain == "IceStorm":
            return self._icestorm_file_templates
        if self.toolchain in ("LSE-iCECube2", "Synplify-iCECube2"):
            return self._icecube2_file_templates
        assert False

    @property
    def command_templates(self):
        if self.toolchain == "IceStorm":
            return self._icestorm_command_templates
        if self.toolchain == "LSE-iCECube2":
            return self._lse_icecube2_command_templates
        if self.toolchain == "Synplify-iCECube2":
            return self._synplify_icecube2_command_templates
        assert False

    @property
    def default_clk_constraint(self):
        # Internal high-speed oscillator: 48 MHz / (2 ^ div)
        if self.default_clk == "SB_HFOSC":
            return Clock(Period(MHz=48 / 2 ** self.hfosc_div))
        # Internal low-speed oscillator: 10 KHz
        elif self.default_clk == "SB_LFOSC":
            return Clock(Period(kHz=10))
        # Otherwise, use the defined Clock resource.
        return super().default_clk_constraint

    def create_missing_domain(self, name):
        # For unknown reasons (no errata was ever published, and no documentation mentions this
        # issue), iCE40 BRAMs read as zeroes for ~3 us after configuration and release of internal
        # global reset. Note that this is a *time-based* delay, generated purely by the internal
        # oscillator, which may not be observed nor influenced directly. For details, see links:
        #  * https://github.com/cliffordwolf/icestorm/issues/76#issuecomment-289270411
        #  * https://github.com/cliffordwolf/icotools/issues/2#issuecomment-299734673
        #
        # To handle this, it is necessary to have a global reset in any iCE40 design that may
        # potentially instantiate BRAMs, and assert this reset for >3 us after configuration.
        # (We add a margin of 5x to allow for PVT variation.) If the board includes a dedicated
        # reset line, this line is ORed with the power on reset.
        #
        # If an internal oscillator is selected as the default clock source, the power-on-reset
        # delay is increased to 100 us, since the oscillators are only stable after that long.
        #
        # The power-on reset timer counts up because the vendor tools do not support initialization
        # of flip-flops.
        if name == "sync" and self.default_clk is not None:
            m = Module()

            # Internal high-speed clock: 6 MHz, 12 MHz, 24 MHz, or 48 MHz depending on the divider.
            if self.default_clk == "SB_HFOSC":
                if not hasattr(self, "hfosc_div"):
                    raise ValueError("SB_HFOSC divider exponent (hfosc_div) must be an integer "
                                     "between 0 and 3")
                if not isinstance(self.hfosc_div, int) or self.hfosc_div < 0 or self.hfosc_div > 3:
                    raise ValueError("SB_HFOSC divider exponent (hfosc_div) must be an integer "
                                     "between 0 and 3, not {!r}"
                                     .format(self.hfosc_div))
                clk_i = Signal()
                m.submodules += Instance("SB_HFOSC",
                                         i_CLKHFEN=1,
                                         i_CLKHFPU=1,
                                         p_CLKHF_DIV=f"0b{self.hfosc_div:02b}",
                                         o_CLKHF=clk_i)
                delay = int(100e-6 * self.default_clk_frequency)
            # Internal low-speed clock: 10 KHz.
            elif self.default_clk == "SB_LFOSC":
                clk_i = Signal()
                m.submodules += Instance("SB_LFOSC",
                                         i_CLKLFEN=1,
                                         i_CLKLFPU=1,
                                         o_CLKLF=clk_i)
                delay = int(100e-6 * self.default_clk_frequency)
            # User-defined clock signal.
            else:
                clk_io = self.request(self.default_clk, dir="-")
                m.submodules.clk_buf = clk_buf = io.Buffer("i", clk_io)
                clk_i = clk_buf.i
                delay = int(15e-6 * self.default_clk_frequency)

            if self.default_rst is not None:
                rst_io = self.request(self.default_rst, dir="-")
                m.submodules.rst_buf = rst_buf = io.Buffer("i", rst_io)
                rst_i = rst_buf.i
            else:
                rst_i = Const(0)

            # Power-on-reset domain
            m.domains += ClockDomain("por", reset_less=True, local=True)
            timer = Signal(range(delay))
            ready = Signal()
            m.d.comb += ClockSignal("por").eq(clk_i)
            with m.If(timer == delay):
                m.d.por += ready.eq(1)
            with m.Else():
                m.d.por += timer.eq(timer + 1)

            # Primary domain
            m.domains += ClockDomain("sync")
            m.d.comb += ClockSignal("sync").eq(clk_i)
            if self.default_rst is not None:
                m.submodules.reset_sync = ResetSynchronizer(~ready | rst_i, domain="sync")
            else:
                m.d.comb += ResetSignal("sync").eq(~ready)

            return m

    def _get_io_buffer_single(self, buffer, port, *, invert_lut=False):
        def get_dff(domain, q, d):
            for bit in range(len(d)):
                m.submodules += Instance("SB_DFF",
                    i_C=ClockSignal(domain),
                    i_D=d[bit],
                    o_Q=q[bit])

        def get_inv(y, a):
            if invert_lut:
                for bit, inv in enumerate(port.invert):
                    m.submodules += Instance("SB_LUT4",
                        p_LUT_INIT=Const(0b01 if inv else 0b10, 16),
                        i_I0=a[bit],
                        i_I1=Const(0),
                        i_I2=Const(0),
                        i_I3=Const(0),
                        o_O=y[bit])
            else:
                mask = sum(int(inv) << bit for bit, inv in enumerate(port.invert))
                if mask == 0:
                    m.d.comb += y.eq(a)
                elif mask == ((1 << len(port)) - 1):
                    m.d.comb += y.eq(~a)
                else:
                    m.d.comb += y.eq(a ^ mask)

        m = Module()

        if isinstance(buffer, io.DDRBuffer):
            if buffer.direction is not io.Direction.Output:
                # Re-register both inputs before they enter fabric. This increases hold time
                # to an entire cycle, and adds one cycle of latency.
                i0 = Signal(len(port))
                i1 = Signal(len(port))
                i0_neg = Signal(len(port))
                i1_neg = Signal(len(port))
                get_inv(i0_neg, i0)
                get_inv(i1_neg, i1)
                get_dff(buffer.i_domain, buffer.i[0], i0_neg)
                get_dff(buffer.i_domain, buffer.i[1], i1_neg)
            if buffer.direction is not io.Direction.Input:
                # Re-register negedge output after it leaves fabric. This increases setup time
                # to an entire cycle, and doesn't add latency.
                o0 = Signal(len(port))
                o1 = Signal(len(port))
                o1_ff = Signal(len(port))
                get_dff(buffer.o_domain, o1_ff, buffer.o[1])
                get_inv(o0, buffer.o[0])
                get_inv(o1, o1_ff)
        else:
            if buffer.direction is not io.Direction.Output:
                i = Signal(len(port))
                get_inv(buffer.i, i)
            if buffer.direction is not io.Direction.Input:
                o = Signal(len(port))
                get_inv(o, buffer.o)

        for bit in range(len(port)):
            attrs = port.io.metadata[bit].attrs

            is_global_input = bool(attrs.get("GLOBAL", False))
            if buffer.direction is io.Direction.Output:
                is_global_input = False
            if is_global_input:
                if port.invert[bit]:
                    raise ValueError("iCE40 global input buffer doesn't support inversion")
                if not isinstance(buffer, io.Buffer):
                    raise ValueError("iCE40 global input buffer cannot be registered")

            io_args = [
                ("io", "PACKAGE_PIN", port.io[bit]),
                *(("p", key, value) for key, value in attrs.items() if key != "GLOBAL"),
            ]

            if buffer.direction is io.Direction.Output:
                # If no input pin is requested, it is important to use a non-registered input pin
                # type, because an output-only pin would not have an input clock, and if its input
                # is configured as registered, this would prevent a co-located input-capable pin
                # from using an input clock.
                i_type =     0b01 # PIN_INPUT
            elif isinstance(buffer, io.Buffer):
                i_type =     0b01 # PIN_INPUT
                if is_global_input:
                    io_args.append(("o", "GLOBAL_BUFFER_OUTPUT", i[bit]))
                else:
                    io_args.append(("o", "D_IN_0", i[bit]))
            elif isinstance(buffer, io.FFBuffer):
                m.submodules += RequirePosedge(buffer.i_domain)
                i_type =     0b00 # PIN_INPUT_REGISTERED aka PIN_INPUT_DDR
                io_args.append(("i", "INPUT_CLK", ClockSignal(buffer.i_domain)))
                io_args.append(("o", "D_IN_0", i[bit]))
            elif isinstance(buffer, io.DDRBuffer):
                m.submodules += RequirePosedge(buffer.i_domain)
                i_type =     0b00 # PIN_INPUT_REGISTERED aka PIN_INPUT_DDR
                io_args.append(("i", "INPUT_CLK", ClockSignal(buffer.i_domain)))
                io_args.append(("o", "D_IN_0", i0[bit]))
                io_args.append(("o", "D_IN_1", i1[bit]))

            if buffer.direction is io.Direction.Input:
                o_type = 0b0000   # PIN_NO_OUTPUT
            elif isinstance(buffer, io.Buffer):
                o_type = 0b1010   # PIN_OUTPUT_TRISTATE
                io_args.append(("i", "D_OUT_0", o[bit]))
            elif isinstance(buffer, io.FFBuffer):
                m.submodules += RequirePosedge(buffer.o_domain)
                o_type = 0b1101   # PIN_OUTPUT_REGISTERED_ENABLE_REGISTERED
                io_args.append(("i", "OUTPUT_CLK", ClockSignal(buffer.o_domain)))
                io_args.append(("i", "D_OUT_0", o[bit]))
            elif isinstance(buffer, io.DDRBuffer):
                m.submodules += RequirePosedge(buffer.o_domain)
                o_type = 0b1100   # PIN_OUTPUT_DDR_ENABLE_REGISTERED
                io_args.append(("i", "OUTPUT_CLK", ClockSignal(buffer.o_domain)))
                io_args.append(("i", "D_OUT_0", o0[bit]))
                io_args.append(("i", "D_OUT_1", o1[bit]))

            io_args.append(("p", "PIN_TYPE", C((o_type << 2) | i_type, 6)))

            if buffer.direction is not io.Direction.Input:
                io_args.append(("i", "OUTPUT_ENABLE", buffer.oe))

            if is_global_input:
                m.submodules[f"buf{bit}"] = Instance("SB_GB_IO", *io_args)
            else:
                m.submodules[f"buf{bit}"] = Instance("SB_IO", *io_args)

        return m

    def get_io_buffer(self, buffer):
        if not isinstance(buffer, (io.Buffer, io.FFBuffer, io.DDRBuffer)):
            raise TypeError(f"Unknown IO buffer type {buffer!r}")
        if isinstance(buffer.port, io.DifferentialPort):
            port_p = io.SingleEndedPort(buffer.port.p, invert=buffer.port.invert,
                                        direction=buffer.port.direction)
            port_n = ~io.SingleEndedPort(buffer.port.n, invert=buffer.port.invert,
                                         direction=buffer.port.direction)
            if buffer.direction is io.Direction.Bidir:
                # Tristate bidirectional buffers are not supported on iCE40 because it requires
                # external termination, which is different for differential pins configured
                # as inputs and outputs.
                raise TypeError("iCE40 does not support bidirectional differential ports")
            elif buffer.direction is io.Direction.Output:
                m = Module()
                invert_lut = isinstance(buffer, io.Buffer)
                m.submodules.p = self._get_io_buffer_single(buffer, port_p, invert_lut=invert_lut)
                m.submodules.n = self._get_io_buffer_single(buffer, port_n, invert_lut=invert_lut)
                return m
            elif buffer.direction is io.Direction.Input:
                # On iCE40, a differential input is placed by only instantiating an SB_IO primitive
                # for the pin with z=0, which is the non-inverting pin. The pinout unfortunately
                # differs between LP/HX and UP series:
                #  * for LP/HX, z=0 is DPxxB   (B is non-inverting, A is inverting)
                #  * for UP,    z=0 is IOB_xxA (A is non-inverting, B is inverting)
                return self._get_io_buffer_single(buffer, port_p, invert_lut=invert_lut)
            else:
                assert False # :nocov:
        elif isinstance(buffer.port, io.SingleEndedPort):
            return self._get_io_buffer_single(buffer, buffer.port)
        else:
            raise TypeError(f"Unknown port type {buffer.port!r}")

    # CDC primitives are not currently specialized for iCE40. It is not known if iCECube2 supports
    # the necessary attributes; nextpnr-ice40 does not.
