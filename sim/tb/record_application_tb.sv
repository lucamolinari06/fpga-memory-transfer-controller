module record_application_tb #(parameter int unsigned ARCH = 0);
    timeunit 1ns; timeprecision 1ps;
    logic clk, rst = 1;
    initial begin clk = 0; forever #5 clk = !clk; end
    logic cmd_valid, cmd_ready;
    logic [31:0] cmd_base_word;
    logic a_req_valid,a_req_ready,a_rsp_valid,a_rsp_ready,a_rsp_last;
    logic [31:0] a_req_base_word,a_rsp_data;
    logic [8:0] a_req_words;
    logic b_req_valid,b_req_ready,b_rsp_valid,b_rsp_ready,b_rsp_last;
    logic [31:0] b_req_base_word,b_rsp_data;
    logic [8:0] b_req_words;
    logic back_req_valid,back_req_ready,back_rsp_valid,back_rsp_ready,back_rsp_last;
    logic [31:0] back_req_base_word,back_rsp_data;
    logic [8:0] back_req_words;
    logic mem_req_valid,mem_req_ready,mem_rsp_valid,mem_rsp_ready,mem_rsp_last;
    logic [31:0] mem_req_base_word,mem_rsp_data;
    logic [8:0] mem_req_words;
    logic out_valid,out_ready,out_last;
    logic [31:0] out_data;
    logic result_valid,result_ready,result_selected;
    logic [31:0] result_id,threshold;
    logic [63:0] result_sum;
    logic [31:0] cache_hits,cache_misses;
    logic preloading = 0,query_started = 0,pre_req_valid = 0,pre_rsp_ready = 0;
    logic [31:0] pre_req_base = 0;
    logic load_ready,b_load_ready,update_valid = 0;
    logic [31:0] update_address = 0,update_data = 0;
    int unsigned load_index,preload_words,preload_cycles;
    int unsigned a_latency,b_latency,a_interval,b_interval,ready_period,ready_cycles;
    int unsigned total,queries,fault,reset_at,reset_applied;
    int unsigned update_epoch,update_writes,first_preload,first_query,write_phase_cycles;
    longint unsigned lifetime_cycle,experiment_origin,write_origin;
    int unsigned driver_index,sent,observed,checked,selected_count,a_beats,b_beats,b_requests,useless_payload;
    int unsigned b_owner_base,b_owner_beat;
    bit b_owner;
    longint unsigned cycle,query_origin,qcycle,memcycle,offer_edge;
    bit offer_pending;
    logic [31:0] oracle [0:2047];
    logic [31:0] order [0:511];
    int unsigned expected_base[$];
    longint unsigned offered_edges[$],command_edges[$];
    string fixture_path,order_path,records_path,metrics_path;
    int record_file,metrics_file,epoch_file,update_file;
    initial begin lifetime_cycle = 0; update_writes = 0; end
    always @(posedge clk) begin
        lifetime_cycle <= lifetime_cycle+1;
        if (update_valid && b_load_ready) update_writes <= update_writes+1;
    end

    assign qcycle = query_started ? cycle-query_origin : 0;
    assign memcycle = query_started ? qcycle : cycle;
    assign cmd_base_word = (fault == 5 && driver_index == 0) ? 32'd2048 : order[driver_index];
    assign result_ready = query_started && !rst && (qcycle % 64'(ready_period) < 64'(ready_cycles))
                          && !(qcycle >= 17 && qcycle < 25);

    if (ARCH == 2) begin : g_header_first
        header_first_controller dut (.*);
    end else begin : g_core
        buffered_transfer_controller #(.BLOCK_WORDS(16),.SPLIT_WORDS(2),.BUFFER_COUNT(2),
            .EARLY_DELIVERY(1),.MODE(ARCH == 1 ? 2 : 1)) dut (.*);
    end
    record_reduce reduce (.*,.in_valid(out_valid),.in_ready(out_ready),.in_data(out_data),.in_last(out_last));
    if (ARCH == 3) begin : g_cache
        record_cache cache (.clk,.rst,.req_valid(b_req_valid),.req_ready(b_req_ready),
            .req_base_word(b_req_base_word),.req_words(b_req_words),.rsp_valid(b_rsp_valid),
            .rsp_ready(b_rsp_ready),.rsp_data(b_rsp_data),.rsp_last(b_rsp_last),
            .mem_req_valid(back_req_valid),.mem_req_ready(back_req_ready),
            .mem_req_base_word(back_req_base_word),.mem_req_words(back_req_words),
            .mem_rsp_valid(back_rsp_valid),.mem_rsp_ready(back_rsp_ready),
            .mem_rsp_data(back_rsp_data),.mem_rsp_last(back_rsp_last),
            .hit_count(cache_hits),.miss_count(cache_misses));
    end else begin : g_direct
        assign back_req_valid = b_req_valid;
        assign b_req_ready = back_req_ready;
        assign back_req_base_word = b_req_base_word;
        assign back_req_words = b_req_words;
        assign b_rsp_valid = back_rsp_valid;
        assign back_rsp_ready = b_rsp_ready;
        assign b_rsp_data = back_rsp_data;
        assign b_rsp_last = back_rsp_last;
        assign cache_hits = 0;
        assign cache_misses = 0;
    end
    assign mem_req_valid = preloading ? pre_req_valid : back_req_valid;
    assign mem_req_base_word = preloading ? pre_req_base : back_req_base_word;
    assign mem_req_words = preloading ? 9'd2 : back_req_words;
    assign mem_rsp_ready = preloading ? pre_rsp_ready && load_ready : back_rsp_ready;
    assign back_req_ready = !preloading && mem_req_ready;
    assign back_rsp_valid = !preloading && mem_rsp_valid;
    assign back_rsp_data = mem_rsp_data;
    assign back_rsp_last = mem_rsp_last;
    application_memory #(.HEADER_MODE(1)) memory_a (.clk,.rst,
        .latency(a_latency),.interval_cycles(a_interval),.accept_period(7),.accept_cycles(5),
        .schedule_cycle(memcycle),.load_valid(preloading && pre_rsp_ready && mem_rsp_valid),
        .load_ready,.load_address(32'(load_index)),.load_data(mem_rsp_data),
        .req_valid(a_req_valid),.req_ready(a_req_ready),.req_base_word(a_req_base_word),
        .req_words(a_req_words),.rsp_valid(a_rsp_valid),.rsp_ready(a_rsp_ready),
        .rsp_data(a_rsp_data),.rsp_last(a_rsp_last));
    application_memory memory_b (.clk,.rst,
        .latency(b_latency),.interval_cycles(b_interval),.accept_period(11),.accept_cycles(8),
        .schedule_cycle(memcycle),.load_valid(update_valid),.load_ready(b_load_ready),.load_address(update_address),.load_data(update_data),
        .req_valid(mem_req_valid),.req_ready(mem_req_ready),.req_base_word(mem_req_base_word),
        .req_words(mem_req_words),.rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),
        .rsp_data(mem_rsp_data),.rsp_last(mem_rsp_last));

    always @(posedge clk) begin
        if (rst) begin cmd_valid <= 0; driver_index <= 0; end
        else if (!query_started) cmd_valid <= 0;
        else if (cmd_valid && cmd_ready) begin cmd_valid <= 0; driver_index <= driver_index+1; end
        else if (!cmd_valid && driver_index < total && qcycle >= 64'(2*driver_index) && qcycle%7 != 3) cmd_valid <= 1;
    end

    // Independent application oracle: accepted logical addresses and the fixture,
    // with no DUT/cache bank index, validity count, split or response ordering.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin : monitor
        int unsigned base;
        longint unsigned offered,accepted;
        logic wanted,got_selected;
        logic [31:0] got_id;
        logic [63:0] wanted_sum,got_sum;
        if (rst) begin
            cycle <= 0; sent = 0; observed = 0; checked = 0; selected_count = 0;
            a_beats = 0; b_beats = 0; b_requests = 0; useless_payload = 0;
            load_index <= 0; preload_words = 0; offer_pending = 0; offer_edge = 0;
            b_owner = 0; b_owner_base = 0; b_owner_beat = 0;
            expected_base.delete(); offered_edges.delete(); command_edges.delete();
        end else begin
            if (preloading && mem_rsp_valid && mem_rsp_ready) begin
                load_index <= load_index+1; preload_words++;
            end
            if (query_started) begin
                if (cmd_valid && !offer_pending) begin offer_edge = qcycle; offer_pending = 1; end
                if (cmd_valid && cmd_ready) begin
                    expected_base.push_back(cmd_base_word);
                    offered_edges.push_back(offer_edge); command_edges.push_back(qcycle);
                    offer_pending = 0; sent++;
                end
                if (a_rsp_valid && a_rsp_ready) a_beats++;
                if (mem_req_valid && mem_req_ready) begin
                    assert (!b_owner) else $fatal(1,"APP_MULTIPLE_B_OWNERS");
                    b_owner = 1; b_owner_base = mem_req_base_word; b_owner_beat = 0; b_requests++;
                end
                if (mem_rsp_valid && mem_rsp_ready) begin
                    assert (b_owner) else $fatal(1,"APP_UNOWNED_B_RESPONSE");
                    base = b_owner_base+b_owner_beat;
                    assert (mem_rsp_data == oracle[base]) else $fatal(1,"APP_BACKING_DATA");
                    if (base%16 >= 2 && oracle[(base/16)*16+1] >= threshold) useless_payload++;
                    b_owner_beat++; b_beats++;
                    if (mem_rsp_last) b_owner = 0;
                end
                if (result_valid && result_ready) begin
                    assert (expected_base.size() > 0) else $fatal(1,"APP_UNEXPECTED_RESULT");
                    observed++;
                    if (!(fault == 4 && observed == total)) begin
                        base = expected_base.pop_front(); offered = offered_edges.pop_front();
                        accepted = command_edges.pop_front(); wanted = oracle[base+1] < threshold;
                        wanted_sum = 0;
                        if (wanted) for (int i = 2; i < 16; i++) wanted_sum += 64'(oracle[base+32'(i)]);
                        got_id = result_id ^ ((fault == 3 && checked == 0) ? 32'd1 : 32'd0);
                        got_selected = result_selected ^ (fault == 2 && checked == 0);
                        got_sum = result_sum ^ ((fault == 1 && checked == 0) ? 64'd1 : 64'd0);
                        assert (got_id == oracle[base]) else $fatal(1,"APP_ID_MISMATCH base=%0d",base);
                        assert (got_selected == wanted) else $fatal(1,"APP_SELECTION_MISMATCH base=%0d",base);
                        assert (got_sum == wanted_sum) else $fatal(1,"APP_SUM_MISMATCH base=%0d",base);
                        if (wanted) selected_count++;
                        $fdisplay(record_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                            checked,base,2*checked,offered,accepted,qcycle,result_id,result_selected,result_sum,
                            a_beats,b_beats,b_requests,cache_hits,cache_misses);
                        checked++;
                    end
                end
            end
            cycle <= cycle+1;
        end
    end
    /* verilator lint_on BLKSEQ */

    task automatic prepare_query;
        if (ARCH == 1 || ARCH == 2) begin
            preloading = 1;
            for (int r = 0; r < 128; r++) begin
                pre_req_base = 32'(r*16); pre_req_valid = 1;
                do @(posedge clk); while (!mem_req_ready);
                @(negedge clk); pre_req_valid = 0; pre_rsp_ready = 1;
                do @(posedge clk); while (!(mem_rsp_valid && mem_rsp_ready && mem_rsp_last));
                @(negedge clk); pre_rsp_ready = 0;
            end
            assert (load_index == 256) else $fatal(1,"APP_PRELOAD_COUNT");
            preloading = 0;
        end
        preload_cycles = 32'(cycle);
        query_origin = cycle; query_started = 1;
    endtask
    task automatic write_metrics(input int handle);
        $fdisplay(handle,"preload_cycles,preload_words,query_cycles,records,selected,a_beats,b_beats,b_requests,useless_payload,cache_hits,cache_misses,reset_applied");
        $fdisplay(handle,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
            preload_cycles,preload_words,qcycle,total,selected_count,a_beats,b_beats,b_requests,useless_payload,cache_hits,cache_misses,reset_applied);
    endtask
    initial begin
        assert (ARCH < 4) else $fatal(1,"APP_ARCH");
        a_latency = 2; a_interval = 1; b_latency = 12; b_interval = 1;
        ready_period = 9; ready_cycles = 6; threshold = 50; queries = 1; fault = 0; reset_at = 0; reset_applied = 0; update_epoch = 0;
        first_preload = 0; first_query = 0; write_phase_cycles = 0; write_origin = 0;
        void'($value$plusargs("a_latency=%d",a_latency)); void'($value$plusargs("a_interval=%d",a_interval));
        void'($value$plusargs("b_latency=%d",b_latency)); void'($value$plusargs("b_interval=%d",b_interval));
        void'($value$plusargs("ready_period=%d",ready_period)); void'($value$plusargs("ready_cycles=%d",ready_cycles));
        void'($value$plusargs("threshold=%d",threshold)); void'($value$plusargs("queries=%d",queries));
        void'($value$plusargs("fault=%d",fault)); void'($value$plusargs("reset_at=%d",reset_at));
        void'($value$plusargs("update_epoch=%d",update_epoch));
        assert ((queries == 1 || queries == 4) && threshold <= 100 && ready_period > 0
                && ready_cycles > 0 && ready_cycles <= ready_period) else $fatal(1,"APP_CONFIG");
        total = 128*queries;
        if (!$value$plusargs("fixture=%s",fixture_path) || !$value$plusargs("order=%s",order_path)
            || !$value$plusargs("records=%s",records_path) || !$value$plusargs("metrics=%s",metrics_path))
            $fatal(1,"APP_INPUTS_REQUIRED");
        $readmemh(fixture_path,oracle); $readmemh(order_path,order);
        record_file = $fopen(update_epoch != 0 ? {records_path,".epoch0.csv"} : records_path,"w");
        metrics_file = $fopen(metrics_path,"w");
        assert (record_file != 0 && metrics_file != 0) else $fatal(1,"APP_OUTPUT_OPEN");
        $fdisplay(record_file,"record,base,release,offered,command,result,id,selected,sum,a_beats,b_beats,b_requests,cache_hits,cache_misses");
        repeat (3) @(posedge clk);
        @(negedge clk); rst = 0;
        experiment_origin = lifetime_cycle;
        prepare_query();
        if (reset_at > 0) begin
            do @(negedge clk); while (qcycle < 64'(reset_at));
            $display("APP_RESET_WITNESS sent=%0d completed=%0d b_owner=%0d held=%0d",sent,observed,b_owner,result_valid&&!result_ready);
            rst = 1; query_started = 0;
            repeat (3) @(posedge clk);
            @(negedge clk); rst = 0; reset_applied = 1;
            $fclose(record_file); record_file = $fopen(records_path,"w");
            $fdisplay(record_file,"record,base,release,offered,command,result,id,selected,sum,a_beats,b_beats,b_requests,cache_hits,cache_misses");
            prepare_query();
        end
        do begin @(posedge clk); #1; end while (observed < total);
        if (update_epoch != 0) begin
            assert (fault == 0 && reset_at == 0 && queries == 1 && threshold == 50)
                else $fatal(1,"APP_UPDATE_CONFIG");
            first_preload = preload_cycles; first_query = 32'(qcycle);
            epoch_file = $fopen({metrics_path,".epoch0.csv"},"w");
            assert (epoch_file != 0) else $fatal(1,"APP_UPDATE_OUTPUT_OPEN");
            write_metrics(epoch_file); $fclose(epoch_file); $fclose(record_file);
            repeat (20) begin @(posedge clk); #1; end
            assert (!b_owner && !result_valid && expected_base.size() == 0) else $fatal(1,"APP_UPDATE_NOT_QUIESCENT");
            @(negedge clk); write_origin = lifetime_cycle;
            update_valid = 1; update_address = 1; update_data = 99;
            do @(posedge clk); while (!b_load_ready);
            @(negedge clk); update_address = 18; update_data = 32'hffffffff;
            do @(posedge clk); while (!b_load_ready);
            @(negedge clk); update_valid = 0;
            write_phase_cycles = 32'(lifetime_cycle-write_origin);
            assert (update_writes == 2) else $fatal(1,"APP_UPDATE_WRITE_COUNT");
            oracle[1] = 99; oracle[18] = 32'hffffffff;
            rst = 1; query_started = 0;
            repeat (3) @(posedge clk);
            @(negedge clk); rst = 0; reset_applied = 1;
            record_file = $fopen(records_path,"w");
            $fdisplay(record_file,"record,base,release,offered,command,result,id,selected,sum,a_beats,b_beats,b_requests,cache_hits,cache_misses");
            prepare_query();
            do begin @(posedge clk); #1; end while (observed < total);
            update_file = $fopen({metrics_path,".update.csv"},"w");
            assert (update_file != 0) else $fatal(1,"APP_UPDATE_OUTPUT_OPEN");
            $fdisplay(update_file,"first_preload_cycles,first_query_cycles,quiet_cycles,write_cycles,writes,reset_cycles,second_preload_cycles,second_query_cycles,total_cycles");
            $fdisplay(update_file,"%0d,%0d,20,%0d,%0d,3,%0d,%0d,%0d",first_preload,first_query,write_phase_cycles,update_writes,
                preload_cycles,qcycle,lifetime_cycle-experiment_origin);
            assert (lifetime_cycle-experiment_origin == 64'(first_preload)+64'(first_query)+20+64'(write_phase_cycles)+3+64'(preload_cycles)+qcycle)
                else $fatal(1,"APP_UPDATE_TIME_ACCOUNTING");
            $fclose(update_file);
            $display("APP_UPDATE_WITNESS writes=%0d first=%0d second=%0d reload=%0d total=%0d",update_writes,first_query,qcycle,preload_cycles,lifetime_cycle-experiment_origin);
        end
        write_metrics(metrics_file);
        repeat (20) begin @(posedge clk); #1; end
        if (fault == 4) begin
            assert (expected_base.size() == 1) else $fatal(1,"APP_FAULT_PENDING");
            $fatal(1,"APP_MISSING_RESULT");
        end
        assert (checked == total && sent == total && expected_base.size() == 0 && !result_valid && !b_owner)
            else $fatal(1,"APP_DRAIN");
        assert (fault == 0) else $fatal(1,"APP_FAULT_NOT_INJECTED");
        $fclose(record_file); $fclose(metrics_file);
        $display("PASS application arch=%0d records=%0d selected=%0d preload=%0d query=%0d",ARCH,checked,selected_count,preload_cycles,qcycle-20);
        $finish;
    end
    assert property (@(posedge clk) disable iff (rst)
        cmd_valid && !cmd_ready |=> cmd_valid && $stable(cmd_base_word)) else $fatal(1,"APP_COMMAND_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        a_req_valid && !a_req_ready |=> a_req_valid && $stable({a_req_base_word,a_req_words})) else $fatal(1,"APP_A_REQUEST_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        b_req_valid && !b_req_ready |=> b_req_valid && $stable({b_req_base_word,b_req_words})) else $fatal(1,"APP_B_REQUEST_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        out_valid && !out_ready |=> out_valid && $stable({out_data,out_last})) else $fatal(1,"APP_STREAM_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        result_valid && !result_ready |=> result_valid && $stable({result_id,result_selected,result_sum})) else $fatal(1,"APP_RESULT_STABILITY");
    initial begin
        if ($test$plusargs("trace")) begin $dumpfile("trace.vcd"); $dumpvars(1,record_application_tb); end
        #20000000; $fatal(1,"APP_TIMEOUT");
    end
endmodule
