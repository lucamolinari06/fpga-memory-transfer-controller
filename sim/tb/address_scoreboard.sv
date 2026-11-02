// The expected order depends ONLY on accepted commands and BLOCK_WORDS.
// No split parameter, memory response, bank address or DUT counter is available here.
module address_scoreboard #(parameter int unsigned BLOCK_WORDS = 8) (
    input logic clk, rst,
    input logic cmd_valid, cmd_ready,
    input logic [31:0] cmd_base_word,
    input logic out_valid, out_ready,
    input logic [31:0] out_data,
    input logic out_last,
    output int unsigned pending_words, checked_words, checked_blocks,
    output longint unsigned expected_checksum
);
    timeunit 1ns; timeprecision 1ps;
    logic [31:0] expected_addresses[$];
    function automatic logic [31:0] source_value(input logic [31:0] address);
        return 32'(64'(address) * 64'h9e3779b1 + 64'ha5a55a5a);
    endfunction
    initial begin
        assert (source_value(0) == 32'ha5a55a5a && source_value(1) == 32'h43dcd40b
                && source_value(256) == 32'hdd1f0b5a && source_value(65535) == 32'h811ee0a9)
            else $fatal(1, "ORACLE_GOLDEN_VECTOR");
    end
    // Imperative simulation-only reference state is updated by this one monitor.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin : check_stream
        logic [31:0] address;
        if (rst) begin
            expected_addresses.delete();
            checked_words = 0;
            checked_blocks = 0;
            expected_checksum = 0;
        end else begin
            if (cmd_valid && cmd_ready)
                for (int unsigned i = 0; i < BLOCK_WORDS; i++)
                    expected_addresses.push_back(cmd_base_word + i);
            if (out_valid && out_ready) begin
                assert (expected_addresses.size() > 0) else $fatal(1, "UNEXPECTED_OUTPUT");
                address = expected_addresses.pop_front();
                assert (out_data == source_value(address))
                    else $fatal(1, "DATA_MISMATCH address=%0d got=%08x expected=%08x", address, out_data, source_value(address));
                assert (out_last == (checked_words % BLOCK_WORDS == BLOCK_WORDS-1))
                    else $fatal(1, "OUTPUT_LAST_MISMATCH");
                expected_checksum = expected_checksum + 64'(source_value(address));
                checked_words++;
                if (out_last) checked_blocks++;
            end
        end
        pending_words = int'(expected_addresses.size());
    end
    /* verilator lint_on BLKSEQ */
endmodule
