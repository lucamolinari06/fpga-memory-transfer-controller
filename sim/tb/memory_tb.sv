module memory_tb;
    timeunit 1ns; timeprecision 1ps;
    logic clk, rst, req_valid, req_ready, rsp_valid, rsp_ready, rsp_last;
    logic [31:0] req_base_word, rsp_data;
    logic [8:0] req_words;
    int unsigned latency, interval_cycles, burst_words, burst_gap, cooldown_cycles, accept_period, accept_cycles;
    longint unsigned cycle, due_edge, next_request_edge;
    int unsigned base, length, beat, requests, completed, stalls;
    bit owned;
    initial clk = 0;
    always #5 clk <= ~clk;
    behavioral_memory memory (.*);
    // Test-only reference schedule uses absolute edge deadlines, not model countdowns.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            cycle = 0; due_edge = 0; next_request_edge = 0;
            base = 0; length = 0; beat = 0; requests = 0; completed = 0; stalls = 0; owned = 0;
        end else begin
            assert (req_ready == (!owned && cycle >= next_request_edge
                    && cycle % 64'(accept_period) < 64'(accept_cycles))) else $fatal(1, "MODEL_REQUEST_SCHEDULE");
            assert (rsp_valid == (owned && cycle >= due_edge)) else $fatal(1, "MODEL_RESPONSE_SCHEDULE");
            if (req_valid && req_ready) begin
                owned = 1; base = req_base_word; length = int'(req_words); beat = 0;
                due_edge = cycle + 64'(latency); requests++;
            end
            if (rsp_valid) begin
                assert (rsp_data == 32'(64'(base+beat)*64'h9e3779b1 + 64'ha5a55a5a))
                    else $fatal(1, "MODEL_DATA");
                assert (rsp_last == (beat+1 == length)) else $fatal(1, "MODEL_LAST");
                if (!rsp_ready) stalls++;
            end
            if (rsp_valid && rsp_ready) begin
                beat++;
                if (beat == length) begin
                    owned = 0; completed++;
                    next_request_edge = cycle + 1 + 64'(cooldown_cycles);
                end else due_edge = cycle + 64'(interval_cycles)
                                    + ((beat % burst_words == 0) ? 64'(burst_gap) : 64'd0);
            end
            cycle++;
        end
    end
    /* verilator lint_on BLKSEQ */
    always @(negedge clk) rsp_ready <= !rst && cycle % 7 < 3;
    task automatic request(input logic [31:0] address, input logic [8:0] words);
        @(negedge clk);
        req_valid = 1; req_base_word = address; req_words = words;
        do @(posedge clk); while (!req_ready);
        @(negedge clk); req_valid = 0;
    endtask
    initial begin
        rst = 1; req_valid = 0; req_base_word = 0; req_words = 0;
        latency = 3; interval_cycles = 2; burst_words = 2; burst_gap = 3;
        cooldown_cycles = 5; accept_period = 3; accept_cycles = 2;
        repeat (3) @(negedge clk);
        rst = 0;
        request(512, 8);
        // Offer the second request while the first is still outstanding.
        request(1024, 3);
        do begin @(posedge clk); #1; end while (completed != 2);
        repeat (12) begin @(posedge clk); #1; end
        assert (requests == 2 && !owned && !rsp_valid && stalls > 0) else $fatal(1, "MODEL_DRAIN");
        $display("PASS memory model: two requests, response stalls=%0d, latency/interval/burst/cooldown", stalls);
        $finish;
    end
    initial begin #100000; $fatal(1, "MODEL_TIMEOUT"); end
endmodule
