module hybrid_tb #(
    parameter int unsigned BLOCK_WORDS = 8,
    parameter int unsigned SPLIT_WORDS = 3
);
    timeunit 1ns; timeprecision 1ps;
    logic clk, rst, cmd_valid, cmd_ready;
    logic [31:0] cmd_base_word;
    logic a_req_valid, a_req_ready, a_rsp_valid, a_rsp_ready, a_rsp_last;
    logic b_req_valid, b_req_ready, b_rsp_valid, b_rsp_ready, b_rsp_last;
    logic [31:0] a_req_base_word, b_req_base_word, a_rsp_data, b_rsp_data;
    logic [8:0] a_req_words, b_req_words;
    logic out_valid, out_ready, out_last;
    logic [31:0] out_data, checked_data;
    int unsigned latency[2], interval_cycles[2], burst_words[2], burst_gap[2], cooldown_cycles[2];
    int unsigned accept_period[2], accept_cycles[2], seg_words[2], seg_offset[2];
    int unsigned sink_period, sink_cycles, stall_start, stall_length, blocks_to_send, reset_case;
    int unsigned expect_early, expect_a_first, expect_b_first, expect_dual_write, expect_hold;
    int unsigned expect_a_before_b_request, expect_b_complete_before_a, expect_last_hold;
    int unsigned pending_words, checked_words, checked_blocks, sent, epoch;
    longint unsigned sink_words, sink_blocks, sink_checksum, expected_checksum;
    logic [1:0] req_valid, req_ready, rsp_valid, rsp_ready, raw_last;
    logic [31:0] req_base[2];
    logic [8:0] req_words[2];
    longint unsigned cycle, command_edge, request_edge[2], response_edge[2], last_consume;
    longint unsigned arrival_edge[256];
    bit arrived[256], seen_request[2], owner[2], allocated;
    int unsigned response_count[2], requests[2], consumed_in_block;
    int unsigned early, a_first, b_first, dual_write, held, held_last, a_before_b_request, b_complete_before_a;
    logic [31:0] accepted_base;
    bit corrupt, bad_a_last;
    int event_file;
    string event_path;
    initial clk = 0;
    always #5 clk <= ~clk;
    hybrid_controller #(.BLOCK_WORDS(BLOCK_WORDS), .SPLIT_WORDS(SPLIT_WORDS)) dut (.*);
    behavioral_memory memory_a (
        .clk, .rst, .latency(latency[0]), .interval_cycles(interval_cycles[0]), .burst_words(burst_words[0]),
        .burst_gap(burst_gap[0]), .cooldown_cycles(cooldown_cycles[0]),
        .accept_period(accept_period[0]), .accept_cycles(accept_cycles[0]),
        .req_valid(a_req_valid), .req_ready(a_req_ready), .req_base_word(a_req_base_word), .req_words(a_req_words),
        .rsp_valid(a_rsp_valid), .rsp_ready(a_rsp_ready), .rsp_data(a_rsp_data), .rsp_last(raw_last[0])
    );
    behavioral_memory memory_b (
        .clk, .rst, .latency(latency[1]), .interval_cycles(interval_cycles[1]), .burst_words(burst_words[1]),
        .burst_gap(burst_gap[1]), .cooldown_cycles(cooldown_cycles[1]),
        .accept_period(accept_period[1]), .accept_cycles(accept_cycles[1]),
        .req_valid(b_req_valid), .req_ready(b_req_ready), .req_base_word(b_req_base_word), .req_words(b_req_words),
        .rsp_valid(b_rsp_valid), .rsp_ready(b_rsp_ready), .rsp_data(b_rsp_data), .rsp_last(raw_last[1])
    );
    assign a_rsp_last = raw_last[0] ^ bad_a_last;
    assign b_rsp_last = raw_last[1];
    assign checked_data = out_data ^ (corrupt ? 32'd1 : 32'd0);
    stream_sink sink (
        .clk, .rst, .period_cycles(sink_period), .ready_cycles(sink_cycles), .stall_start, .stall_length,
        .valid(out_valid), .ready(out_ready), .data(checked_data), .last(out_last),
        .words(sink_words), .blocks(sink_blocks), .checksum(sink_checksum)
    );
    address_scoreboard #(.BLOCK_WORDS(BLOCK_WORDS)) scoreboard (
        .clk, .rst, .cmd_valid, .cmd_ready, .cmd_base_word, .out_valid, .out_ready,
        .out_data(checked_data), .out_last, .pending_words, .checked_words, .checked_blocks, .expected_checksum
    );
    assign req_valid = {b_req_valid, a_req_valid};
    assign req_ready = {b_req_ready, a_req_ready};
    assign rsp_valid = {b_rsp_valid, a_rsp_valid};
    assign rsp_ready = {b_rsp_ready, a_rsp_ready};
    assign req_base[0] = a_req_base_word;
    assign req_base[1] = b_req_base_word;
    assign req_words[0] = a_req_words;
    assign req_words[1] = b_req_words;
    always @(negedge clk) begin
        cmd_valid <= !rst && sent < blocks_to_send;
        cmd_base_word <= 32'(256 + epoch*8192 + sent*BLOCK_WORDS);
    end
    // Public-channel protocol/timing reference, independent of DUT internals.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            sent = 0; cycle = 0; command_edge = 0; last_consume = 0;
            allocated = 0; accepted_base = 0; consumed_in_block = 0;
            early = 0; a_first = 0; b_first = 0; dual_write = 0; held = 0; held_last = 0;
            a_before_b_request = 0; b_complete_before_a = 0;
            for (int i=0; i<2; i++) begin
                requests[i] = 0; response_count[i] = 0; owner[i] = 0; seen_request[i] = 0;
                request_edge[i] = 0; response_edge[i] = 0;
            end
            for (int i=0; i<256; i++) begin arrived[i] = 0; arrival_edge[i] = 0; end
            $fdisplay(event_file, "0,reset,%0d,0,0", epoch);
        end else begin
            if (cmd_valid && cmd_ready) begin
                assert (!allocated && !owner[0] && !owner[1]) else $fatal(1, "MONITOR_SLOT_REUSE");
                allocated = 1; accepted_base = cmd_base_word; sent++; command_edge = cycle; consumed_in_block = 0;
                for (int i=0; i<2; i++) begin response_count[i] = 0; seen_request[i] = 0; end
                for (int i=0; i<256; i++) arrived[i] = 0;
                $fdisplay(event_file, "%0d,command,%0d,%0d,%0d", cycle, epoch, cmd_base_word, BLOCK_WORDS);
            end
            // Count first-arrival witnesses before updating either interface's reference count.
            if (seg_words[0] > 0 && seg_words[1] > 0) begin
                if (a_rsp_valid && a_rsp_ready && response_count[0] == 0 && response_count[1] == 0 && !b_rsp_valid) a_first++;
                if (b_rsp_valid && b_rsp_ready && response_count[1] == 0 && response_count[0] == 0 && !a_rsp_valid) b_first++;
                if (a_rsp_valid && a_rsp_ready && b_rsp_valid && b_rsp_ready) dual_write++;
                if (b_rsp_valid && b_rsp_ready && raw_last[1] && response_count[0] == 0 && !a_rsp_valid) b_complete_before_a++;
            end
            for (int i=0; i<2; i++) begin
                if (seg_words[i] == 0) begin
                    assert (!req_valid[i] && !rsp_ready[i] && !rsp_valid[i]) else $fatal(1, "EMPTY_SEGMENT_ACTIVITY");
                end else begin
                    if (allocated && cycle > command_edge && !seen_request[i])
                        assert (req_valid[i]) else $fatal(1, "REQUEST_INDEPENDENCE");
                    if (req_valid[i] && req_ready[i]) begin
                        assert (allocated && !seen_request[i] && !owner[i]) else $fatal(1, "REQUEST_OWNERSHIP");
                        assert (req_base[i] == accepted_base + seg_offset[i] && int'(req_words[i]) == seg_words[i])
                            else $fatal(1, "REQUEST_MAPPING");
                        requests[i]++; seen_request[i] = 1; owner[i] = 1; request_edge[i] = cycle;
                        $fdisplay(event_file, "%0d,request_%0d,%0d,%0d,%0d", cycle, i, epoch, req_base[i], req_words[i]);
                    end
                    if (rsp_valid[i] && rsp_ready[i]) begin
                        assert (owner[i] && response_count[i] < seg_words[i]) else $fatal(1, "UNOWNED_RESPONSE");
                        if (response_count[i] == 0)
                            assert (cycle == request_edge[i] + 64'(latency[i])) else $fatal(1, "INITIAL_LATENCY");
                        else assert (cycle == response_edge[i] + 64'(interval_cycles[i])
                                     + ((response_count[i] % burst_words[i] == 0) ? 64'(burst_gap[i]) : 64'd0))
                            else $fatal(1, "BEAT_INTERVAL");
                        assert (raw_last[i] == (response_count[i]+1 == seg_words[i])) else $fatal(1, "MEMORY_LAST");
                        assert (!arrived[seg_offset[i]+response_count[i]]) else $fatal(1, "DUPLICATE_WRITE_ADDRESS");
                        arrived[seg_offset[i]+response_count[i]] = 1;
                        arrival_edge[seg_offset[i]+response_count[i]] = cycle;
                        $fdisplay(event_file, "%0d,response_%0d,%0d,%0d,%0d", cycle, i, epoch,
                                  req_base[i]+response_count[i], int'(raw_last[i]));
                        response_count[i]++; response_edge[i] = cycle;
                        if (raw_last[i]) owner[i] = 0;
                    end
                end
            end
            if (out_valid && !out_ready) begin
                held++;
                if (out_last) held_last++;
                $fdisplay(event_file, "%0d,hold,%0d,%0d,%0d", cycle, epoch, accepted_base+consumed_in_block, int'(out_last));
            end
            if (out_valid && out_ready) begin
                assert (allocated && arrived[consumed_in_block]) else $fatal(1, "OUTPUT_BEFORE_ARRIVAL");
                assert (cycle >= arrival_edge[consumed_in_block]+2) else $fatal(1, "SYNC_READ_LATENCY");
                if (sink_period == 1 && stall_length == 0) begin
                    if (consumed_in_block == 0) assert (cycle == arrival_edge[0]+2) else $fatal(1, "FIRST_WORD_LATENCY");
                    else assert (cycle == ((arrival_edge[consumed_in_block]+2 > last_consume+1)
                                           ? arrival_edge[consumed_in_block]+2 : last_consume+1))
                        else $fatal(1, "STREAM_BUBBLE");
                end
                if (response_count[0]+response_count[1] < BLOCK_WORDS) early++;
                if (seg_words[1] > 0 && !seen_request[1]) a_before_b_request++;
                $fdisplay(event_file, "%0d,consume,%0d,%0d,%0d", cycle, epoch, accepted_base+consumed_in_block, int'(out_last));
                consumed_in_block++; last_consume = cycle;
                if (out_last) begin
                    assert (consumed_in_block == BLOCK_WORDS && !owner[0] && !owner[1]) else $fatal(1, "PREMATURE_RELEASE");
                    allocated = 0;
                end
            end
            cycle++;
        end
    end
    /* verilator lint_on BLKSEQ */
    initial begin
        rst = 1; epoch = 0;
        seg_words[0] = SPLIT_WORDS;
        seg_words[1] = BLOCK_WORDS >= SPLIT_WORDS ? BLOCK_WORDS-SPLIT_WORDS : 0;
        seg_offset[0] = 0; seg_offset[1] = SPLIT_WORDS;
        latency[0] = 2; latency[1] = 6; interval_cycles[0] = 3; interval_cycles[1] = 1;
        for (int i=0; i<2; i++) begin
            burst_words[i] = 256; burst_gap[i] = 0; cooldown_cycles[i] = 0;
            accept_period[i] = 1; accept_cycles[i] = 1;
        end
        sink_period = 1; sink_cycles = 1; stall_start = 0; stall_length = 0;
        blocks_to_send = 6; reset_case = 0;
        expect_early = 0; expect_a_first = 0; expect_b_first = 0; expect_dual_write = 0;
        expect_hold = 0; expect_last_hold = 0; expect_a_before_b_request = 0; expect_b_complete_before_a = 0;
        corrupt = $test$plusargs("corrupt"); bad_a_last = $test$plusargs("bad_a_last");
        void'($value$plusargs("a_latency=%d", latency[0]));
        void'($value$plusargs("a_interval=%d", interval_cycles[0]));
        void'($value$plusargs("a_burst=%d", burst_words[0]));
        void'($value$plusargs("a_gap=%d", burst_gap[0]));
        void'($value$plusargs("a_cooldown=%d", cooldown_cycles[0]));
        void'($value$plusargs("a_accept_period=%d", accept_period[0]));
        void'($value$plusargs("a_accept_cycles=%d", accept_cycles[0]));
        void'($value$plusargs("b_latency=%d", latency[1]));
        void'($value$plusargs("b_interval=%d", interval_cycles[1]));
        void'($value$plusargs("b_burst=%d", burst_words[1]));
        void'($value$plusargs("b_gap=%d", burst_gap[1]));
        void'($value$plusargs("b_cooldown=%d", cooldown_cycles[1]));
        void'($value$plusargs("b_accept_period=%d", accept_period[1]));
        void'($value$plusargs("b_accept_cycles=%d", accept_cycles[1]));
        void'($value$plusargs("sink_period=%d", sink_period));
        void'($value$plusargs("sink_cycles=%d", sink_cycles));
        void'($value$plusargs("stall_start=%d", stall_start));
        void'($value$plusargs("stall_length=%d", stall_length));
        void'($value$plusargs("blocks=%d", blocks_to_send));
        void'($value$plusargs("reset_case=%d", reset_case));
        void'($value$plusargs("expect_early=%d", expect_early));
        void'($value$plusargs("expect_a_first=%d", expect_a_first));
        void'($value$plusargs("expect_b_first=%d", expect_b_first));
        void'($value$plusargs("expect_dual_write=%d", expect_dual_write));
        void'($value$plusargs("expect_hold=%d", expect_hold));
        void'($value$plusargs("expect_last_hold=%d", expect_last_hold));
        void'($value$plusargs("expect_a_before_b_request=%d", expect_a_before_b_request));
        void'($value$plusargs("expect_b_complete_before_a=%d", expect_b_complete_before_a));
        if (!$value$plusargs("events=%s", event_path)) event_path = "events.csv";
        event_file = $fopen(event_path, "w");
        assert (event_file != 0) else $fatal(1, "EVENT_LOG_OPEN");
        $fdisplay(event_file, "edge,event,epoch,address,value");
        if ($test$plusargs("trace")) begin $dumpfile("failure.vcd"); $dumpvars; end
        repeat (3) @(negedge clk);
        rst = 0;
        if (reset_case != 0) begin
            case (reset_case)
                1: begin do @(negedge clk); while (!(seen_request[0] && !seen_request[1])); end
                2: begin do @(negedge clk); while (!(seen_request[1] && !seen_request[0])); end
                3: begin do @(negedge clk); while (!(response_count[1] == seg_words[1] && response_count[0] == 0)); end
                4: begin do @(negedge clk); while (!(response_count[0] > 0 && response_count[0] < seg_words[0])); end
                5: begin do @(negedge clk); while (!(out_valid && !out_ready)); end
                6: begin do @(negedge clk); while (!(out_valid && !out_ready && out_last)); end
                default: $fatal(1, "RESET_CASE");
            endcase
            rst = 1; epoch = 1;
            repeat (2) @(negedge clk);
            rst = 0;
        end
        do begin @(posedge clk); #1; end while (checked_blocks != blocks_to_send);
        repeat (20) begin @(posedge clk); #1; end
        assert (pending_words == 0 && !allocated && !owner[0] && !owner[1] && !out_valid && cmd_ready)
            else $fatal(1, "DRAIN_CHECK");
        for (int i=0; i<2; i++)
            assert (requests[i] == (seg_words[i] == 0 ? 0 : blocks_to_send)) else $fatal(1, "REQUEST_TOTAL");
        assert (sink_words == 64'(checked_words) && sink_blocks == 64'(checked_blocks) && sink_checksum == expected_checksum)
            else $fatal(1, "SINK_ACCOUNTING");
        if (expect_early != 0) assert (early > 0) else $fatal(1, "EARLY_WITNESS");
        if (expect_a_first != 0) assert (a_first > 0) else $fatal(1, "A_FIRST_WITNESS");
        if (expect_b_first != 0) assert (b_first > 0) else $fatal(1, "B_FIRST_WITNESS");
        if (expect_dual_write != 0) assert (dual_write > 0) else $fatal(1, "DUAL_WRITE_WITNESS");
        if (expect_hold != 0) assert (held > 0) else $fatal(1, "HOLD_WITNESS");
        if (expect_last_hold != 0) assert (held_last > 0) else $fatal(1, "LAST_HOLD_WITNESS");
        if (expect_a_before_b_request != 0) assert (a_before_b_request > 0) else $fatal(1, "REQUEST_INDEPENDENCE_WITNESS");
        if (expect_b_complete_before_a != 0) assert (b_complete_before_a > 0) else $fatal(1, "SUFFIX_EARLY_WITNESS");
        $display("PASS hybrid N=%0d S=%0d blocks=%0d words=%0d early=%0d Afirst=%0d Bfirst=%0d dual=%0d held=%0d reset=%0d",
                 BLOCK_WORDS, SPLIT_WORDS, checked_blocks, checked_words, early, a_first, b_first, dual_write, held, reset_case);
        $fclose(event_file); $finish;
    end
    initial begin #2000000; $fatal(1, "TEST_TIMEOUT"); end
endmodule
