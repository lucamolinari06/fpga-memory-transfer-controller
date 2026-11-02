// Readiness is based solely on elapsed reset-relative cycles, never on DUT valid.
module stream_sink (
    input logic clk, rst,
    input int unsigned period_cycles, ready_cycles, stall_start, stall_length,
    input logic valid,
    output logic ready,
    input logic [31:0] data,
    input logic last,
    output longint unsigned words, blocks, checksum
);
    timeunit 1ns; timeprecision 1ps;
    longint unsigned cycle;
    assign ready = !rst && (cycle % 64'(period_cycles)) < 64'(ready_cycles)
                   && !(cycle >= 64'(stall_start) && cycle < 64'(stall_start) + 64'(stall_length));
    always @(posedge clk) begin
        if (rst) begin
            cycle <= 0;
            words <= 0;
            blocks <= 0;
            checksum <= 0;
        end else begin
            assert (period_cycles >= 1 && ready_cycles >= 1 && ready_cycles <= period_cycles)
                else $fatal(1, "SINK_CONFIG");
            cycle <= cycle + 1;
            if (valid && ready) begin
                words <= words + 1;
                checksum <= checksum + 64'(data);
                if (last) blocks <= blocks + 1;
            end
        end
    end
endmodule
