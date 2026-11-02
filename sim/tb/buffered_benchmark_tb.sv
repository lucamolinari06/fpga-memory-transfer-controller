// Common harness: all measurement state comes from public handshakes.
module buffered_benchmark_tb #(
    parameter int unsigned BLOCK_WORDS = 8,
    parameter int unsigned SPLIT_WORDS = 3,
    parameter int unsigned MODE = 0, // 0=A-only, 1=B-only, 2=hybrid
    parameter bit EARLY_DELIVERY = 1,
    parameter int unsigned BUFFER_COUNT = 2,
    parameter bit PROFILED = 0
);
    timeunit 1ns; timeprecision 1ps;
    logic clk, rst, cmd_valid, cmd_ready;
    logic [31:0] cmd_base_word;
    logic a_req_valid, a_req_ready, a_rsp_valid, a_rsp_ready, a_rsp_last;
    logic b_req_valid, b_req_ready, b_rsp_valid, b_rsp_ready, b_rsp_last;
    logic [31:0] a_req_base_word, b_req_base_word, a_rsp_data, b_rsp_data;
    logic [8:0] a_req_words, b_req_words;
    logic out_valid, out_ready, out_last;
    logic [31:0] out_data;
    int unsigned latency[2], interval_cycles[2], burst_words[2], burst_gap[2], cooldown_cycles[2];
    int unsigned accept_period[2], accept_cycles[2];
    int unsigned sink_period, sink_cycles, stall_start, stall_length, blocks_to_send, warmup;
    int unsigned pending_words, checked_words, checked_blocks, sent, done, in_block, arrived[2];
    longint unsigned sink_words, sink_blocks, sink_checksum, expected_checksum;
    logic [1:0] req_valid, req_ready, rsp_valid, rsp_ready, rsp_last;
    logic [31:0] req_base[2];
    logic [8:0] req_words[2];
    int unsigned allocated, next_request[2], owner_record[2];
    bit owner[2];
    int unsigned segment[2], offset[2], received[2];
    logic [31:0] accepted_base[2];
    longint cycle, command_edge[2], first_edge[2], request_edge[2][2], response_first[2][2], response_last[2][2];
    longint arrival[2][256];
    // Cumulative edge counts; snapshot on final consumption, including that edge.
    longint grant_count, occupancy_max;
    longint useful, unavailable, intentional, held, slot_sum, backlog_sum;
    longint requests[2], beats[2], offered[2], blocked[2], busy[2], early_words;
    int unsigned backlog, backlog_max, steady_backlog_max;
    int file, event_file;
    int unsigned reset_at, base_shift, progress_limit, second_edge, fault;
    logic [31:0] checked_data;
    logic checked_last, checked_valid;
    bit witness[8];
    longint last_progress;
    string event_path;
    string path;
    initial clk = 0;
    always #5 clk <= ~clk;
    buffered_transfer_controller #(.BLOCK_WORDS(BLOCK_WORDS),.SPLIT_WORDS(SPLIT_WORDS),
        .EARLY_DELIVERY(EARLY_DELIVERY),.BUFFER_COUNT(BUFFER_COUNT),.MODE(MODE)) dut (.*);
    if (BUFFER_COUNT==1) begin : g_reference
        logic ref_cmd_ready,ref_a_req_valid,ref_a_rsp_ready,ref_b_req_valid,ref_b_rsp_ready,ref_out_valid,ref_out_last;
        logic [31:0] ref_a_req_base_word,ref_b_req_base_word,ref_out_data;
        logic [8:0] ref_a_req_words,ref_b_req_words;
        if (MODE==2) begin : g_hybrid
            hybrid_controller #(.BLOCK_WORDS(BLOCK_WORDS),.SPLIT_WORDS(SPLIT_WORDS),.EARLY_DELIVERY(EARLY_DELIVERY)) reference (.cmd_ready(ref_cmd_ready), .a_req_valid(ref_a_req_valid), .a_req_base_word(ref_a_req_base_word), .a_req_words(ref_a_req_words), .a_rsp_ready(ref_a_rsp_ready), .b_req_valid(ref_b_req_valid), .b_req_base_word(ref_b_req_base_word), .b_req_words(ref_b_req_words), .b_rsp_ready(ref_b_rsp_ready), .out_valid(ref_out_valid), .out_data(ref_out_data), .out_last(ref_out_last), .*);
        end else begin : g_baseline
            single_memory_controller #(.BLOCK_WORDS(BLOCK_WORDS),.SPLIT_WORDS(SPLIT_WORDS),.EARLY_DELIVERY(EARLY_DELIVERY),.USE_B(MODE==1)) reference (.cmd_ready(ref_cmd_ready), .a_req_valid(ref_a_req_valid), .a_req_base_word(ref_a_req_base_word), .a_req_words(ref_a_req_words), .a_rsp_ready(ref_a_rsp_ready), .b_req_valid(ref_b_req_valid), .b_req_base_word(ref_b_req_base_word), .b_req_words(ref_b_req_words), .b_rsp_ready(ref_b_rsp_ready), .out_valid(ref_out_valid), .out_data(ref_out_data), .out_last(ref_out_last), .*);
        end
        always @(posedge clk) if (!rst) begin
            assert ({cmd_ready,a_req_valid,a_rsp_ready,b_req_valid,b_rsp_ready,out_valid}==
                {ref_cmd_ready,ref_a_req_valid,ref_a_rsp_ready,ref_b_req_valid,ref_b_rsp_ready,ref_out_valid}) else $fatal(1,"REFERENCE_CHANNEL");
            if (out_valid) assert ({out_data,out_last}=={ref_out_data,ref_out_last}) else $fatal(1,"REFERENCE_OUTPUT");
            if (a_req_valid) assert ({a_req_base_word,a_req_words}=={ref_a_req_base_word,ref_a_req_words}) else $fatal(1,"REFERENCE_A");
            if (b_req_valid) assert ({b_req_base_word,b_req_words}=={ref_b_req_base_word,ref_b_req_words}) else $fatal(1,"REFERENCE_B");
        end
    end
    int unsigned profile;
    logic [31:0] rsp_data[2];
    logic [1:0] grant;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [1:0] eligible;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [3:0] reserved;
    longint unsigned epoch, row_hits, row_closed, row_conflicts, grants[2];
    /* verilator lint_off UNUSEDSIGNAL */
    longint unsigned responses[2], maintenance_starts;
    /* verilator lint_on UNUSEDSIGNAL */
    longint valid_first[2][2], reserved_edges[4], pause_episodes;
    bit previous_pause;
    logic [31:0] workload[8192];
    string workload_path;
    if (PROFILED) begin : g_profiled
        profiled_memory_pair memory_pair(.*);
        service_monitor monitor(.*);
    end else begin : g_simple
        for (genvar i=0;i<2;i++) begin : g_memory
            behavioral_memory memory (.clk,.rst,.latency(latency[i]),.interval_cycles(interval_cycles[i]),
                .burst_words(burst_words[i]),.burst_gap(burst_gap[i]),.cooldown_cycles(cooldown_cycles[i]),
                .accept_period(accept_period[i]),.accept_cycles(accept_cycles[i]),
                .req_valid(req_valid[i]),.req_ready(req_ready[i]),.req_base_word(req_base[i]),.req_words(req_words[i]),
                .rsp_valid(rsp_valid[i]),.rsp_ready(rsp_ready[i]),.rsp_data(rsp_data[i]),.rsp_last(rsp_last[i]));
        end
        assign grant=0; assign eligible=0; assign reserved=0; assign epoch=64'(cycle);
        assign row_hits=0;assign row_closed=0;assign row_conflicts=0;assign maintenance_starts=0;
        for (genvar i=0;i<2;i++) begin : g_no_counters
            assign grants[i]=0;assign responses[i]=0;
        end
    end
    assign a_req_ready=req_ready[0];
    assign b_req_ready=req_ready[1];
    assign a_rsp_valid=rsp_valid[0];
    assign b_rsp_valid=rsp_valid[1];
    assign a_rsp_data=rsp_data[0];
    assign b_rsp_data=rsp_data[1];
    assign a_rsp_last=rsp_last[0];
    assign b_rsp_last=rsp_last[1];
    stream_sink sink (
        .clk, .rst, .period_cycles(sink_period), .ready_cycles(sink_cycles), .stall_start, .stall_length,
        .valid(out_valid), .ready(out_ready), .data(out_data), .last(out_last),
        .words(sink_words), .blocks(sink_blocks), .checksum(sink_checksum)
    );
    assign checked_data = fault==1 ? out_data^32'd1 : fault==3 ? 32'hdd1f0b5a : out_data;
    assign checked_last = fault==2 ? !out_last : out_last;
    assign checked_valid = fault==4 ? 1'b0 : out_valid;
    address_scoreboard #(.BLOCK_WORDS(BLOCK_WORDS)) scoreboard (
        .clk, .rst, .cmd_valid, .cmd_ready, .cmd_base_word, .out_valid(checked_valid), .out_ready,
        .out_data(checked_data), .out_last(checked_last), .pending_words, .checked_words, .checked_blocks, .expected_checksum
    );
    assign req_valid = {b_req_valid, a_req_valid};
    assign rsp_ready = {b_rsp_ready, a_rsp_ready};
    assign req_base[0] = a_req_base_word;
    assign req_base[1] = b_req_base_word;
    assign req_words[0] = a_req_words;
    assign req_words[1] = b_req_words;
    always @(negedge clk) begin
        cmd_valid <= !rst && sent < blocks_to_send && (sent!=1 || cycle>=64'(second_edge));
        // Repeat the same 128 aligned blocks: no cache exists in this model.
        cmd_base_word <= workload[sent % 8192]+base_shift;
    end
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            for (int i=0;i<4;i++) reserved_edges[i]=0;
            pause_episodes=0; previous_pause=0;
            last_progress=0;
            for (int i=0;i<8;i++) witness[i]=0;
            cycle = 0; sent = 0; done = 0; in_block = 0;
            allocated = 0;
            grant_count=0;occupancy_max=0;
            useful = 0; unavailable = 0; intentional = 0; held = 0;
            slot_sum = 0; backlog_sum = 0; backlog = 0; backlog_max = 0;
            steady_backlog_max = 0; early_words = 0;
            for (int i=0; i<2; i++) begin
                owner[i] = 0; next_request[i]=0; owner_record[i]=0; received[i] = 0;
                 requests[i] = 0; beats[i] = 0; offered[i] = 0; blocked[i] = 0; busy[i] = 0;
            end
            for (int r=0;r<2;r++) begin
                accepted_base[r]=0;command_edge[r]=-1;first_edge[r]=-1;arrived[r]=0;
                for (int i=0;i<2;i++) begin request_edge[r][i]=-1;response_first[r][i]=-1;response_last[r][i]=-1;valid_first[r][i]=-1;end
                for (int i=0;i<256;i++) arrival[r][i]=-1;
            end
        end else begin
            if ((cmd_valid && cmd_ready) || |(req_valid & req_ready) || |(rsp_valid & rsp_ready) ||
                (out_valid && out_ready)) last_progress=cycle;
            assert (cycle-last_progress<64'(progress_limit)) else $fatal(1,"BENCH_NO_PROGRESS");
            if (event_file!=0) begin
                if (cmd_valid && cmd_ready) $fdisplay(event_file,"%0d,command,%0d,0",cycle,cmd_base_word);
                for (int i=0;i<2;i++) begin
                    if (req_valid[i] && req_ready[i]) $fdisplay(event_file,"%0d,request%0d,%0d,%0d",cycle,i,req_base[i],req_words[i]);
                    if (rsp_valid[i] && rsp_ready[i]) $fdisplay(event_file,"%0d,response%0d,%0d,%0d",cycle,i,rsp_data[i],rsp_last[i]);
                end
                if (dut.read_fire) $fdisplay(event_file,"%0d,read,%0d,%0d",cycle,dut.head,dut.reads[dut.head]);
                if (|grant) $fdisplay(event_file,"%0d,grant,%0d,0",cycle,grant);
                if (out_valid && out_ready) $fdisplay(event_file,"%0d,output,%0d,%0d",cycle,out_data,out_last);
            end
            if (allocated==2) witness[0]=1;
            if (owner[0] && owner[1] && owner_record[0]!=owner_record[1]) witness[1]=1;
            if (out_valid && !out_ready && out_last) witness[2]=1;
            if (cmd_valid && cmd_ready && out_valid && out_ready && out_last) witness[3]=1;
            if ((dut.pending[0] || dut.pending[1]) && out_valid && out_ready && out_last) witness[4]=1;
            if (|(req_valid & ~req_ready)) witness[5]=1;
            if (reserved[2]) witness[6]=1;
            if (out_valid && out_ready && |(rsp_valid & rsp_ready) &&
                ((owner[0] && owner_record[0]!=done%2) || (owner[1] && owner_record[1]!=done%2))) witness[7]=1;
            grant_count+=64'(grant[0])+64'(grant[1]);
            assert (epoch==64'(cycle)) else $fatal(1,"CALENDAR_EPOCH");
            if (done < blocks_to_send) begin
                for (int i=0;i<4;i++) if (reserved[i]) reserved_edges[i]++;
                if (reserved[2] && !previous_pause) pause_episodes++;
                previous_pause=reserved[2];
                if (out_ready && out_valid) useful++;
                if (out_ready && !out_valid) unavailable++;
                if (!out_ready) intentional++;
                if (out_valid && !out_ready) held++;
                for (int i=0; i<2; i++) begin
                    // Pre-edge outstanding: (request edge, final response edge].
                    if (owner[i]) busy[i]++;
                    if (rsp_valid[i]) offered[i]++;
                    if (rsp_valid[i] && !rsp_ready[i]) blocked[i]++;
                end
            end
            if (cmd_valid && cmd_ready) begin
                assert (allocated < BUFFER_COUNT) else $fatal(1,"BENCH_REUSE");
                assert (sent < blocks_to_send) else $fatal(1,"BENCH_EXTRA_COMMAND");
                allocated++; accepted_base[sent%2]=cmd_base_word;command_edge[sent%2]=cycle;
                first_edge[sent%2]=-1;arrived[sent%2]=0;
                for (int i=0;i<2;i++) begin
                    request_edge[sent%2][i]=-1;response_first[sent%2][i]=-1;
                    response_last[sent%2][i]=-1;valid_first[sent%2][i]=-1;
                end
                for (int i=0;i<256;i++) arrival[sent%2][i]=-1;
                sent++;
            end
            for (int i=0; i<2; i++) begin
                if (segment[i] == 0) assert (!req_valid[i] && !rsp_valid[i] && !rsp_ready[i])
                    else $fatal(1, "BENCH_EMPTY_INTERFACE");
                if (req_valid[i] && req_ready[i]) begin
                    assert (next_request[i]<sent && !owner[i] && cycle > command_edge[next_request[i]%2])
                        else $fatal(1, "BENCH_REQUEST_OWNERSHIP");
                    assert (req_base[i] == accepted_base[next_request[i]%2]+offset[i] && int'(req_words[i]) == segment[i])
                        else $fatal(1, "BENCH_REQUEST_MAPPING");
                    owner_record[i]=next_request[i]%2; next_request[i]++; received[i]=0;
                    request_edge[owner_record[i]][i] = cycle; owner[i] = 1; requests[i]++;
                end
                if (rsp_valid[i] && valid_first[owner_record[i]][i]<0) valid_first[owner_record[i]][i]=cycle;
                if (rsp_valid[i] && rsp_ready[i]) begin
                    assert (owner[i] && received[i] < segment[i]) else $fatal(1, "BENCH_RESPONSE_OWNERSHIP");
                    if (received[i] == 0) begin
                        assert (cycle >= request_edge[owner_record[i]][i]+64'(latency[i])) else $fatal(1,"BENCH_LATENCY");
                        response_first[owner_record[i]][i] = cycle;
                    end else assert (cycle >= response_last[owner_record[i]][i]+64'(interval_cycles[i]))
                        else $fatal(1,"BENCH_INTERVAL");
                    assert (rsp_last[i] == (received[i]+1 == segment[i])) else $fatal(1, "BENCH_RESPONSE_LAST");
                    arrival[owner_record[i]][offset[i]+received[i]] = cycle;
                    received[i]++; arrived[owner_record[i]]++; beats[i]++; response_last[owner_record[i]][i] = cycle;
                    if (rsp_last[i]) owner[i] = 0;
                end
            end
            if (out_valid && out_ready) begin
                assert (allocated>0 && in_block < BLOCK_WORDS && arrival[done%2][in_block] >= 0
                        && cycle >= arrival[done%2][in_block]+2) else $fatal(1, "BENCH_SYNC_LATENCY");
                if (!EARLY_DELIVERY) assert (arrived[done%2] == BLOCK_WORDS &&
                    cycle >= ((response_last[done%2][0] > response_last[done%2][1]) ? response_last[done%2][0] : response_last[done%2][1])+2)
                    else $fatal(1, "BENCH_FULL_BLOCK_GATE");
                if (in_block == 0) first_edge[done%2] = cycle;
                if (arrived[done%2] < BLOCK_WORDS) early_words++;
                in_block++;
                assert (out_last == (in_block == BLOCK_WORDS)) else $fatal(1, "BENCH_OUTPUT_LAST");
                if (out_last) begin
                    assert (!(owner[0] && owner_record[0]==done%2) && !(owner[1] && owner_record[1]==done%2) && arrived[done%2] == BLOCK_WORDS) else $fatal(1, "BENCH_RELEASE");
                    allocated--;
                end
            end
            if (done < blocks_to_send) begin
                // Post-edge logical occupancy, including the word held at the output.
                assert (beats[0]+beats[1] >= useful) else $fatal(1, "BENCH_BACKLOG");
                backlog = 32'(beats[0]+beats[1]-useful);
                assert (backlog<=BUFFER_COUNT*BLOCK_WORDS && allocated<=BUFFER_COUNT) else $fatal(1,"BENCH_CAPACITY");
                if (64'(allocated)>occupancy_max) occupancy_max=64'(allocated);
                slot_sum += 64'(allocated); backlog_sum += 64'(backlog);
                if (backlog > backlog_max) backlog_max = backlog;
                if (done >= warmup && backlog > steady_backlog_max) steady_backlog_max = backlog;
            end
            if (out_valid && out_ready && out_last) begin
                $fwrite(file, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d", done, accepted_base[done%2],
                    command_edge[done%2], request_edge[done%2][0], request_edge[done%2][1], response_first[done%2][0], response_first[done%2][1],
                    response_last[done%2][0], response_last[done%2][1], first_edge[done%2], cycle);
                $fwrite(file, ",%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d", useful, unavailable, intentional,
                    held, slot_sum, backlog_sum, backlog_max, steady_backlog_max, early_words);
                for (int i=0; i<2; i++)
                    $fwrite(file, ",%0d,%0d,%0d,%0d,%0d", requests[i], beats[i], offered[i], blocked[i], busy[i]);
                $fwrite(file, ",%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",valid_first[done%2][0],valid_first[done%2][1],
                    row_hits,row_closed,row_conflicts,grants[0],grants[1],pause_episodes);
                for (int i=0;i<4;i++) $fwrite(file,",%0d",reserved_edges[i]);
                $fwrite(file,",%0d,%0d,%0d,%0d,%0d\n",sent,allocated,backlog,grant_count,occupancy_max);
                done++; in_block=0;
            end
            cycle++;
        end
    end
    /* verilator lint_on BLKSEQ */
    initial begin
        event_file=0;reset_at=0;base_shift=0;progress_limit=100000;second_edge=0;fault=0;
        void'($value$plusargs("second_edge=%d",second_edge));
        void'($value$plusargs("fault=%d",fault));
        void'($value$plusargs("progress_limit=%d",progress_limit));
        void'($value$plusargs("reset_at=%d",reset_at));
        if ($value$plusargs("eventlog=%s",event_path)) event_file=$fopen(event_path,"w");
        profile=1;
        void'($value$plusargs("profile=%d",profile));
        if (!$value$plusargs("workload=%s",workload_path)) $fatal(1,"WORKLOAD_REQUIRED");
        $readmemh(workload_path,workload);
        rst = 1; blocks_to_send = 1088; warmup = 64;
        assert (profile<=3 && (!PROFILED || profile>=1)) else $fatal(1,"BENCH_PROFILE");
        assert (MODE <= 2) else $fatal(1, "BENCH_MODE");
        segment[0] = MODE == 0 ? BLOCK_WORDS : (MODE == 2 ? SPLIT_WORDS : 0);
        segment[1] = MODE == 1 ? BLOCK_WORDS : (MODE == 2 ? BLOCK_WORDS-SPLIT_WORDS : 0);
        offset[0] = 0; offset[1] = MODE == 2 ? SPLIT_WORDS : 0;
        latency[0] = 2; latency[1] = 6; interval_cycles[0] = 3; interval_cycles[1] = 1;
        for (int i=0; i<2; i++) begin
            burst_words[i] = 256; burst_gap[i] = 0; cooldown_cycles[i] = 0;
            accept_period[i] = 1; accept_cycles[i] = 1;
        end
        sink_period = 1; sink_cycles = 1; stall_start = 0; stall_length = 0;
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
        void'($value$plusargs("warmup=%d", warmup));
        assert (warmup >= 1 && blocks_to_send > warmup) else $fatal(1, "BENCH_WINDOW_CONFIG");
        if (!$value$plusargs("records=%s", path)) $fatal(1, "BENCH_RECORDS_REQUIRED");
        file = $fopen(path, "w");
        assert (file != 0) else $fatal(1, "BENCH_LOG_OPEN");
        $fwrite(file, "block,base,command,request_a,request_b,response_first_a,response_first_b,response_last_a,response_last_b,first,last");
        $fwrite(file, ",useful,unavailable,intentional,held,slot_sum,backlog_sum,backlog_max,steady_backlog_max,early_words");
        $fwrite(file, ",a_requests,a_beats,a_offered,a_blocked,a_busy,b_requests,b_beats,b_offered,b_blocked,b_busy");
        $fdisplay(file,",valid_first_a,valid_first_b,row_hits,row_closed,row_conflicts,a_grants,b_grants,pause_episodes,reserved_a,reserved_b,maintenance,shared_reserved,commands,occupancy,backlog,grant_count,occupancy_max");
        // Release between clock edges; driver offers command for edge 0 in every run.
        repeat (3) @(posedge clk);
        #1; rst = 0;
        if (reset_at>0) begin
            repeat (reset_at) @(posedge clk);
            
            #1;
            $display("RESET_WITNESS occupied=%0d activeA=%0d activeB=%0d pendingA=%0d pendingB=%0d held=%0d last=%0d maintenance=%0d",allocated,dut.active[0],dut.active[1],dut.pending[0],dut.pending[1],out_valid&&!out_ready,out_last,reserved[2]);
            @(negedge clk);rst=1;base_shift=32768;
            repeat (2) @(posedge clk);
            @(negedge clk);rst=0;
        end
        do begin @(posedge clk); #1; end while (fault==4 ? done != blocks_to_send : checked_blocks != blocks_to_send);
        repeat (20) begin @(posedge clk); #1; end
        if (fault==4) begin
            assert (pending_words==blocks_to_send*BLOCK_WORDS) else $fatal(1,"FAULT_NOT_INJECTED");
            $fatal(1,"CHECKER_MISSING_OUTPUT");
        end
        assert (pending_words == 0 && allocated==0 && !owner[0] && !owner[1] && !out_valid && cmd_ready)
            else $fatal(1, "BENCH_DRAIN");
        assert (sent == blocks_to_send && done == blocks_to_send && checked_words == blocks_to_send*BLOCK_WORDS)
            else $fatal(1, "BENCH_TOTALS");
        assert (sink_words == 64'(checked_words) && sink_blocks == 64'(checked_blocks) && sink_checksum == expected_checksum)
            else $fatal(1, "BENCH_SINK_ACCOUNTING");
        if (fault==4) $fatal(1,"CHECKER_MISSING_OUTPUT");
        $display("WITNESSES full=%0d split_owner=%0d held_last=%0d simultaneous=%0d pending_retire=%0d request_stall=%0d maintenance=%0d overlap=%0d",witness[0],witness[1],witness[2],witness[3],witness[4],witness[5],witness[6],witness[7]);
        $display("PASS benchmark N=%0d S=%0d mode=%0d early=%0d blocks=%0d words=%0d checksum=%0d",
            BLOCK_WORDS, SPLIT_WORDS, MODE, EARLY_DELIVERY, checked_blocks, checked_words, expected_checksum);
        $fclose(file); if (event_file!=0) $fclose(event_file); $finish;
    end
    initial begin
        if ($test$plusargs("trace")) begin $dumpfile("trace.vcd");$dumpvars(1,buffered_benchmark_tb);end
    end
    initial begin #100000000; $fatal(1, "BENCH_TIMEOUT"); end
endmodule
