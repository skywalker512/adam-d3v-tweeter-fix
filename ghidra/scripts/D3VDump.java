import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.lang.*;
import ghidra.program.model.symbol.*;
import ghidra.app.cmd.disassemble.ArmDisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import java.io.*;
import java.math.BigInteger;

public class D3VDump extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs().length > 0 ? getScriptArgs()[0] : ".";
        Memory mem = currentProgram.getMemory();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        if (mem.getBlock("RAM") == null) {
            MemoryBlock b = mem.createUninitializedBlock("RAM", sp.getAddress(0x20000000L), 0x4000, false);
            b.setRead(true); b.setWrite(true);
            b = mem.createUninitializedBlock("PERIPH", sp.getAddress(0x40000000L), 0x200000, false);
            b.setRead(true); b.setWrite(true); b.setVolatile(true);
            b = mem.createUninitializedBlock("SCS", sp.getAddress(0xE000E000L), 0x1000, false);
            b.setRead(true); b.setWrite(true); b.setVolatile(true);
        }
        long romEnd = mem.getBlock(sp.getAddress(0x2000L)).getEnd().getOffset();
        Register tmode = currentProgram.getRegister("TMode");
        for (int i = 4; i < 0xC0; i += 4) { long BASE = 0x2000L;
            long v = mem.getInt(sp.getAddress(0x2000L + i)) & 0xffffffffL;
            if ((v & 1) == 1 && v < romEnd) {
                Address a = sp.getAddress(v & ~1L);
                new ArmDisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
                new CreateFunctionCmd(a).applyTo(currentProgram, monitor);
                if (i == 4) currentProgram.getSymbolTable().createLabel(a, "Reset_Handler", SourceType.USER_DEFINED);
            }
        }
        analyzeAll(currentProgram);
        // sweep for PUSH {..., lr} prologues in undefined bytes
        Listing listing = currentProgram.getListing();
        for (long ea = 0x20C0L; ea < 0x5c38L; ea += 2) {
            Address a = sp.getAddress(ea);
            if (listing.getInstructionContaining(a) != null) continue;
            if (listing.getDefinedDataContaining(a) != null) continue;
            int w = mem.getShort(a) & 0xffff;
            if ((w & 0xFF00) == 0xB500) {
                new ArmDisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
                new CreateFunctionCmd(a).applyTo(currentProgram, monitor);
            }
        }
        analyzeAll(currentProgram);

        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        PrintWriter c = new PrintWriter(new FileWriter(outDir + "/decomp.c"));
        PrintWriter s = new PrintWriter(new FileWriter(outDir + "/disasm.txt"));
        FunctionIterator it = listing.getFunctions(true);
        int n = 0;
        while (it.hasNext()) {
            Function f = it.next();
            n++;
            s.println("\n; ===== " + f.getName() + " @ " + f.getEntryPoint() + " =====");
            InstructionIterator ii = listing.getInstructions(f.getBody(), true);
            while (ii.hasNext()) {
                Instruction ins = ii.next();
                StringBuilder refs = new StringBuilder();
                for (Reference r : ins.getReferencesFrom()) {
                    if (r.getReferenceType().isData()) {
                        Address t = r.getToAddress();
                        refs.append(" ; ->").append(t);
                        try { if (mem.contains(t) && mem.getBlock(t).isInitialized()) refs.append("=").append(String.format("%08x", mem.getInt(t))); } catch (Exception e) {}
                    }
                }
                s.println(ins.getAddress() + "  " + ins.toString() + refs);
            }
            DecompileResults r = di.decompileFunction(f, 120, monitor);
            c.println("\n// ===== " + f.getName() + " @ 0x" + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses() + " =====");
            if (r != null && r.decompileCompleted()) c.println(r.getDecompiledFunction().getC());
            else c.println("// DECOMPILE FAILED: " + (r == null ? "null" : r.getErrorMessage()));
        }
        c.close(); s.close();
        println("D3VDump: functions=" + n);
    }
}
