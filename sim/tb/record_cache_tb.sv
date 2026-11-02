// Native cache unit verification: fixture-backed memory, independent address oracle.
module record_cache_tb;
    timeunit 1ns; timeprecision 1ps;
    logic clk;
    initial clk = 0;
    always #5 clk = !clk;
    logic rst, req_valid, req_ready, rsp_valid, rsp_ready, rsp_last;
    logic [31:0] req_base_word, rsp_data;
    logic [8:0] req_words;
    logic mem_req_valid, mem_req_ready, mem_rsp_valid, mem_rsp_ready, mem_rsp_last;
    logic [31:0] mem_req_base_word, mem_rsp_data, hit_count, miss_count;
    logic [8:0] mem_req_words;
    record_cache dut (.*);

    logic [31:0] fixture [0:2047];
    string fixture_path;
    int scenario, cycle, total_cycles, backend_requests, completed, output_stalls, request_stalls;
    int expected_index, accepted_at, memory_next, memory_due;
    logic expected_active, memory_active, block_requests, block_output;
    logic [31:0] expected_base, memory_base;
    logic bad_last, corrupt_data;
    logic was_hit;

    function automatic logic [31:0] expected_word(input logic [31:0] address);
        return (address * 32'h9e3779b1) ^ 32'ha5c31f27;
    endfunction

    assign mem_req_ready = !rst && !memory_active && !block_requests && cycle % 7 < 3;
    assign rsp_ready = !rst && !block_output && cycle % 9 < 4;

    // The backend owns a registered response. Clock-based release opportunities
    // cannot withdraw an already offered beat or change it during a stall.
    always @(posedge clk) begin
        if (rst) begin
            cycle <= 0;
            memory_active <= 0;
            memory_base <= 0;
            memory_next <= 0;
            memory_due <= 0;
            mem_rsp_valid <= 0;
            mem_rsp_data <= 0;
            mem_rsp_last <= 0;
        end else begin
            cycle <= cycle + 1;
            if (mem_rsp_valid && mem_rsp_ready) begin
                mem_rsp_valid <= 0;
                if (mem_rsp_last) memory_active <= 0;
            end
            if (mem_req_valid && mem_req_ready) begin
                assert (!memory_active && mem_req_words == 16
                        && mem_req_base_word[3:0] == 0 && mem_req_base_word < 2048)
                    else $fatal(1, "UNIT_BACKEND_REQUEST");
                memory_active <= 1;
                memory_base <= mem_req_base_word;
                memory_next <= 0;
                memory_due <= cycle + 3;
            end
            if (memory_active && memory_next < 16 && cycle >= memory_due
                && cycle % 5 != 1 && (!mem_rsp_valid || mem_rsp_ready)) begin
                mem_rsp_valid <= 1;
                mem_rsp_data <= fixture[11'(memory_base + 32'(memory_next))]
                    ^ ((corrupt_data && memory_next == 5) ? 32'h1 : 32'h0);
                mem_rsp_last <= memory_next == 15 || (bad_last && memory_next == 3);
                memory_next <= memory_next + 1;
                memory_due <= cycle + 2;
            end
        end
    end

    // The oracle sees only accepted frontend addresses and output handshakes.
    // It does not use DUT tags/indices/validity or memory response data.
    always @(posedge clk) begin
        if (rst) begin
            expected_active <= 0;
            expected_base <= 0;
            expected_index <= 0;
            accepted_at <= 0;
            was_hit <= 0;
        end else begin
            if (req_valid && req_ready) begin
                assert (!expected_active) else $fatal(1, "UNIT_MULTIPLE_REQUESTS");
                expected_active <= 1;
                expected_base <= req_base_word;
                expected_index <= 0;
                accepted_at <= cycle;
                // Counter updates at the accepted edge; first output later
                // records whether a backend request occurred, without DUT state.
                was_hit <= 1;
            end
            if (mem_req_valid && mem_req_ready) begin
                assert (expected_active && mem_req_base_word == expected_base)
                    else $fatal(1, "UNIT_WRONG_BACKEND_ADDRESS");
                backend_requests <= backend_requests + 1;
                was_hit <= 0;
            end
            if (mem_req_valid && !mem_req_ready) request_stalls <= request_stalls + 1;
            if (rsp_valid && !rsp_ready) output_stalls <= output_stalls + 1;
            if (rsp_valid && rsp_ready) begin
                assert (expected_active && expected_index < 16)
                    else $fatal(1, "UNIT_UNEXPECTED_OUTPUT");
                assert (rsp_data == expected_word(expected_base + 32'(expected_index)))
                    else $fatal(1, "CACHE_DATA_MISMATCH address=%0d", expected_base + 32'(expected_index));
                assert (rsp_last == (expected_index == 15))
                    else $fatal(1, "UNIT_OUTPUT_LAST");
                if (was_hit && expected_index == 0)
                    assert (cycle >= accepted_at + 2) else $fatal(1, "UNIT_ASYNC_HIT_BYPASS");
                expected_index <= expected_index + 1;
                if (rsp_last) begin
                    expected_active <= 0;
                    completed <= completed + 1;
                end
            end
        end
        total_cycles <= total_cycles + 1;
        if (total_cycles > 5000) $fatal(1, "UNIT_TIMEOUT");
    end

    task automatic reset_all;
        @(negedge clk);
        rst = 1;
        req_valid = 0;
        repeat (2) @(posedge clk);
        @(negedge clk);
        assert (!rsp_valid && !mem_req_valid && !mem_rsp_ready)
            else $fatal(1, "UNIT_RESET_CHANNELS");
        rst = 0;
    endtask

    task automatic offer(input logic [31:0] base_word, input logic [8:0] words);
        @(negedge clk);
        req_base_word = base_word;
        req_words = words;
        req_valid = 1;
        do @(posedge clk); while (!req_ready);
        @(negedge clk);
        req_valid = 0;
    endtask

    task automatic transfer(input logic [31:0] base_word);
        offer(base_word, 9'd16);
        wait (!expected_active);
        @(negedge clk);
    endtask

    initial begin
        rst = 1;
        req_valid = 0;
        req_base_word = 0;
        req_words = 16;
        block_requests = 0;
        block_output = 0;
        bad_last = 0;
        corrupt_data = 0;
        total_cycles = 0;
        backend_requests = 0;
        completed = 0;
        output_stalls = 0;
        request_stalls = 0;
        scenario = 0;
        if (!$value$plusargs("fixture=%s", fixture_path)) $fatal(1, "UNIT_FIXTURE_MISSING");
        if ($value$plusargs("scenario=%d", scenario)) begin end
        $readmemh(fixture_path, fixture);
        reset_all();
        case (scenario)
            0: begin
                transfer(0); transfer(0); transfer(256); transfer(0); transfer(16); transfer(16);
                assert (hit_count == 2 && miss_count == 4 && backend_requests == 4 && completed == 6)
                    else $fatal(1, "UNIT_CACHE_COUNTS");
                assert (output_stalls > 0 && request_stalls > 0) else $fatal(1, "UNIT_STALL_WITNESS");
            end
            1: begin
                block_requests = 1;
                offer(32, 16);
                wait (mem_req_valid && !mem_req_ready);
                repeat (3) @(negedge clk);
                reset_all();
                block_requests = 0;
                transfer(32); transfer(32);
                assert (hit_count == 1 && miss_count == 1 && backend_requests == 1)
                    else $fatal(1, "UNIT_PENDING_RESET_COUNTS");
            end
            2: begin
                offer(48, 16);
                wait (expected_index >= 4);
                reset_all();
                transfer(48); transfer(48);
                assert (hit_count == 1 && miss_count == 1 && backend_requests == 2)
                    else $fatal(1, "UNIT_REFILL_RESET_COUNTS");
            end
            3: begin
                transfer(64);
                block_output = 1;
                offer(64, 16);
                wait (rsp_valid && !rsp_ready);
                repeat (3) @(negedge clk);
                reset_all();
                block_output = 0;
                transfer(64); transfer(64);
                assert (hit_count == 1 && miss_count == 1 && backend_requests == 2)
                    else $fatal(1, "UNIT_HIT_RESET_COUNTS");
            end
            4: begin
                block_output = 1;
                offer(80, 16);
                wait (rsp_valid && !rsp_ready);
                repeat (3) @(negedge clk);
                reset_all();
                block_output = 0;
                transfer(80); transfer(80);
                assert (hit_count == 1 && miss_count == 1 && backend_requests == 2)
                    else $fatal(1, "UNIT_HELD_MISS_RESET_COUNTS");
            end
            5: offer(1, 16);
            6: offer(0, 15);
            7: offer(2048, 16);
            8: begin bad_last = 1; transfer(96); end
            9: begin corrupt_data = 1; transfer(112); end
            default: $fatal(1, "UNIT_UNKNOWN_SCENARIO");
        endcase
        repeat (20) @(negedge clk);
        assert (!expected_active && !rsp_valid && !mem_req_valid && !mem_rsp_valid)
            else $fatal(1, "UNIT_QUIET_DRAIN");
        $display("PASS record_cache scenario=%0d completed=%0d backend_requests=%0d hit=%0d miss=%0d output_stalls=%0d request_stalls=%0d", scenario, completed, backend_requests, hit_count, miss_count, output_stalls, request_stalls);
        $finish;
    end
endmodule
