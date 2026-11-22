import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.app.cmd.disassemble.ArmDisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.pcode.JumpTable;
import java.util.ArrayList;

public class SwitchFix extends GhidraScript {
    @Override
    public void run() throws Exception {
        currentProgram.getMemory().getBlock(toAddr(0x2000L)).setWrite(false);
        Function h = getFunctionAt(toAddr(0x3c82L));
        h.setCallFixup("switch8_r3");
        clearListing(toAddr(0x4356L), toAddr(0x461bL));
        long[] tg = {0x4360, 0x4370, 0x4380, 0x4390, 0x43a2, 0x4422, 0x44a8, 0x4552, 0x4550};
        ArrayList<Address> t = new ArrayList<>();
        for (long a : tg) {
            t.add(toAddr(a));
            new ArmDisassembleCommand(toAddr(a), null, true).applyTo(currentProgram, monitor);
            currentProgram.getReferenceManager().addMemoryReference(toAddr(0x4352L), toAddr(a), RefType.COMPUTED_JUMP, SourceType.USER_DEFINED, 0);
        }
        Function f = getFunctionAt(toAddr(0x434cL));
        CreateFunctionCmd.fixupFunctionBody(currentProgram, f, monitor);
        new JumpTable(toAddr(0x4352L), t, true, 0).writeOverride(f);
        println("body bytes after fix: " + f.getBody().getNumAddresses());
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        DecompileResults r = di.decompileFunction(f, 120, monitor);
        java.io.PrintWriter w = new java.io.PrintWriter(getScriptArgs().length > 0 ? getScriptArgs()[0] : "led_set_state.c");
        w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "FAILED " + r.getErrorMessage());
        w.close();
    }
}
