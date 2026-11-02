// One synchronous write port and one enabled synchronous read port.
// No reset on array or read data; the owning controller resets validity.
module sync_bank #(
    parameter int unsigned WORDS = 8
) (
    input logic clk,
    input logic wr_en,
    input logic [8:0] wr_addr,
    input logic [31:0] wr_data,
    input logic rd_en,
    input logic [8:0] rd_addr,
    output logic [31:0] rd_data
);
    timeunit 1ns; timeprecision 1ps;
    logic [31:0] mem [0:WORDS-1];
    always_ff @(posedge clk) begin
        if (wr_en) mem[int'(wr_addr)] <= wr_data;
        if (rd_en) rd_data <= mem[int'(rd_addr)];
    end
    // synthesis translate_off
    initial assert (WORDS >= 1 && WORDS <= 256) else $fatal(1, "BANK_PARAMETER");
    always @(posedge clk) begin
        if (wr_en) assert (int'(wr_addr) < WORDS) else $fatal(1, "BANK_WRITE_BOUNDS");
        if (rd_en) assert (int'(rd_addr) < WORDS) else $fatal(1, "BANK_READ_BOUNDS");
        assert (!(wr_en && rd_en && wr_addr == rd_addr)) else $fatal(1, "BANK_COLLISION");
    end
    // synthesis translate_on
endmodule
