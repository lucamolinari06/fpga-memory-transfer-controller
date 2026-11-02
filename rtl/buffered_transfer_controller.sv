module buffered_transfer_controller #(
    parameter int unsigned BLOCK_WORDS = 8,
    parameter int unsigned SPLIT_WORDS = 3,
    parameter bit EARLY_DELIVERY = 1,
    parameter int unsigned BUFFER_COUNT = 2,
    parameter int unsigned MODE = 2
) (
    input logic clk, rst,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic [31:0] cmd_base_word,
    output logic a_req_valid,
    input logic a_req_ready,
    output logic [31:0] a_req_base_word,
    output logic [8:0] a_req_words,
    input logic a_rsp_valid,
    output logic a_rsp_ready,
    input logic [31:0] a_rsp_data,
    input logic a_rsp_last,
    output logic b_req_valid,
    input logic b_req_ready,
    output logic [31:0] b_req_base_word,
    output logic [8:0] b_req_words,
    input logic b_rsp_valid,
    output logic b_rsp_ready,
    input logic [31:0] b_rsp_data,
    input logic b_rsp_last,
    output logic out_valid,
    input logic out_ready,
    output logic [31:0] out_data,
    output logic out_last
);
    timeunit 1ns; timeprecision 1ps;
    localparam int C = BUFFER_COUNT == 2 ? 2 : 1;
    localparam int SUFFIX = BLOCK_WORDS >= SPLIT_WORDS ? BLOCK_WORDS-SPLIT_WORDS : 0;
    logic allocated[C], issued[C][2];
    logic [31:0] base[C];
    logic [8:0] committed[C][2], reads[C], consumed[C];
    int unsigned head, tail, occupancy;
    logic active[2], pending[2];
    int unsigned owner[2], pending_slot[2], selected[2];
    logic found[2];
    logic [8:0] received[2], length[2];
    logic [1:0] req_valid, req_ready, rsp_valid, rsp_ready, rsp_last;
    logic [31:0] req_base[2], rsp_data[2];
    logic [8:0] req_words[2];
    logic wr[C][2];
    logic [31:0] wr_data[C][2], bank_data[C][2];
    logic output_valid, output_last, output_bank;
    int unsigned output_slot;
    logic read_fire, read_bank, readable, enqueue, retire;
    logic [8:0] read_addr;
    assign req_ready = {b_req_ready,a_req_ready};
    assign rsp_valid = {b_rsp_valid,a_rsp_valid};
    assign rsp_last = {b_rsp_last,a_rsp_last};
    assign rsp_data[0] = a_rsp_data;
    assign rsp_data[1] = b_rsp_data;
    assign {b_req_valid,a_req_valid} = req_valid;
    assign {b_rsp_ready,a_rsp_ready} = rsp_ready;
    assign a_req_base_word = req_base[0];
    assign b_req_base_word = req_base[1];
    assign a_req_words = req_words[0];
    assign b_req_words = req_words[1];
    assign length[0] = 9'(MODE == 0 ? BLOCK_WORDS : MODE == 2 ? SPLIT_WORDS : 0);
    assign length[1] = 9'(MODE == 1 ? BLOCK_WORDS : MODE == 2 ? SUFFIX : 0);
    assign cmd_ready = !rst && occupancy < C;
    assign enqueue = cmd_valid && cmd_ready;
    assign out_valid = !rst && output_valid;
    assign out_last = output_last;
    assign out_data = bank_data[output_slot][output_bank];
    assign retire = out_valid && out_ready && out_last;
    if (SPLIT_WORDS == 0) begin : g_all_suffix
        assign read_bank = 1;
    end
    else begin : g_partition
        assign read_bank = reads[head] >= 9'(SPLIT_WORDS);
    end
    assign read_addr = read_bank ? reads[head]-9'(SPLIT_WORDS) : reads[head];
    assign readable = read_addr < committed[head][read_bank];
    assign read_fire = !rst && allocated[head] && reads[head] < 9'(BLOCK_WORDS)
        && readable && (!output_valid || out_ready)
        && (EARLY_DELIVERY || committed[head][0]+committed[head][1] == 9'(BLOCK_WORDS));

    always_comb begin
        for (int i=0;i<2;i++) begin
            selected[i]=head; found[i]=0;
            // Search in FIFO age order; pending selection pins an offered descriptor.
            for (int age=0;age<C;age++) begin
                if (!found[i] && allocated[(head+32'(age))%C] && !issued[(head+32'(age))%C][i]) begin
                    selected[i]=(head+32'(age))%C; found[i]=1;
                end
            end
            if (pending[i]) begin selected[i]=pending_slot[i]; found[i]=1; end
            req_valid[i]=!rst && !active[i] && found[i] && length[i]!=0;
            req_base[i]=base[selected[i]]+32'(MODE == 2 && i == 1 ? SPLIT_WORDS : 0);
            req_words[i]=length[i];
            rsp_ready[i]=!rst && active[i] && received[i]<length[i];
        end
        for (int s=0;s<C;s++) for (int b=0;b<2;b++) begin
            wr[s][b]=0; wr_data[s][b]=0;
            for (int i=0;i<2;i++) begin
                if (rsp_valid[i] && rsp_ready[i] && owner[i]==32'(s)
                    && (MODE==2 ? i==b : (int'(received[i])<int'(SPLIT_WORDS) ? b==0 : b==1))) begin
                    wr[s][b]=1; wr_data[s][b]=rsp_data[i];
                end
            end
        end
    end
    for (genvar s=0;s<C;s++) begin : g_slot
        if (SPLIT_WORDS>0) begin : g_prefix
            sync_bank #(.WORDS(SPLIT_WORDS<=256 ? SPLIT_WORDS : 1)) bank (
                .clk,.wr_en(wr[s][0]),.wr_addr(committed[s][0]),.wr_data(wr_data[s][0]),
                .rd_en(read_fire && head==s && !read_bank),.rd_addr(read_addr),.rd_data(bank_data[s][0]));
        end else begin : g_no_prefix
            assign bank_data[s][0]=0;
        end
        if (SUFFIX>0) begin : g_suffix
            sync_bank #(.WORDS(SUFFIX<=256 ? SUFFIX : 1)) bank (
                .clk,.wr_en(wr[s][1]),.wr_addr(committed[s][1]),.wr_data(wr_data[s][1]),
                .rd_en(read_fire && head==s && read_bank),.rd_addr(read_addr),.rd_data(bank_data[s][1]));
        end else begin : g_no_suffix
            assign bank_data[s][1]=0;
        end
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            head<=0;tail<=0;occupancy<=0;
            output_valid<=0;output_last<=0;output_bank<=0;output_slot<=0;
            for (int i=0;i<2;i++) begin active[i]<=0;pending[i]<=0;owner[i]<=0;pending_slot[i]<=0;received[i]<=0;end
            for (int s=0;s<C;s++) begin
                allocated[s]<=0;base[s]<=0;reads[s]<=0;consumed[s]<=0;
                for (int b=0;b<2;b++) begin issued[s][b]<=0;committed[s][b]<=0;end
            end
        end else begin
            case ({enqueue,retire})
                2'b10: occupancy<=occupancy+1;
                2'b01: occupancy<=occupancy-1;
                default: ;
            endcase
            if (enqueue) begin
                allocated[tail]<=1;base[tail]<=cmd_base_word;reads[tail]<=0;consumed[tail]<=0;
                for (int b=0;b<2;b++) begin issued[tail][b]<=0;committed[tail][b]<=0;end
                tail <= C==1 ? 0 : 1-tail;
            end
            for (int i=0;i<2;i++) begin
                if (req_valid[i] && !req_ready[i]) begin pending[i]<=1;pending_slot[i]<=selected[i];end
                if (req_valid[i] && req_ready[i]) begin
                    pending[i]<=0;active[i]<=1;owner[i]<=selected[i];received[i]<=0;issued[selected[i]][i]<=1;
                end
                if (rsp_valid[i] && rsp_ready[i]) begin
                    received[i]<=received[i]+9'd1;
                    if (rsp_last[i]) active[i]<=0;
                end
            end
            for (int s=0;s<C;s++) for (int b=0;b<2;b++)
                if (wr[s][b]) committed[s][b]<=committed[s][b]+9'd1;
            if (read_fire) begin
                reads[head]<=reads[head]+9'd1;
                output_valid<=1;output_last<=reads[head]==9'(BLOCK_WORDS-1);
                output_slot<=head;output_bank<=read_bank;
            end else if (out_valid && out_ready) output_valid<=0;
            if (out_valid && out_ready) consumed[head]<=consumed[head]+9'd1;
            if (retire) begin allocated[head]<=0;head<= C==1 ? 0 : 1-head;end
        end
    end
    // synthesis translate_off
    initial begin
        assert (BUFFER_COUNT==1 || BUFFER_COUNT==2) else $fatal(1,"PARAM_BUFFER_COUNT");
        assert (MODE<=2) else $fatal(1,"PARAM_MODE");
        assert (BLOCK_WORDS>=1 && BLOCK_WORDS<=256 && (BLOCK_WORDS & (BLOCK_WORDS-1))==0) else $fatal(1,"PARAM_BLOCK_WORDS");
        assert (SPLIT_WORDS<=BLOCK_WORDS) else $fatal(1,"PARAM_SPLIT_WORDS");
    end
    assert property (@(posedge clk) disable iff(rst) out_valid && !out_ready |=> out_valid && $stable({out_data,out_last})) else $fatal(1,"OUTPUT_STABILITY");
    assert property (@(posedge clk) disable iff(rst) a_req_valid && !a_req_ready |=> a_req_valid && $stable({a_req_base_word,a_req_words})) else $fatal(1,"A_REQUEST_STABILITY");
    assert property (@(posedge clk) disable iff(rst) b_req_valid && !b_req_ready |=> b_req_valid && $stable({b_req_base_word,b_req_words})) else $fatal(1,"B_REQUEST_STABILITY");
    always @(posedge clk) if (!rst) begin : check
        int count, outstanding;
        count=0;outstanding=0;
        assert (occupancy<=C && head<C && tail<C) else $fatal(1,"FIFO_BOUNDS");
        if (enqueue) begin
            assert (!allocated[tail]) else $fatal(1,"ALLOCATED_REUSE");
            assert (cmd_base_word%BLOCK_WORDS==0) else $fatal(1,"COMMAND_ALIGNMENT");
            assert ({1'b0,cmd_base_word}+33'(BLOCK_WORDS-1)<=33'h0ffffffff) else $fatal(1,"COMMAND_OVERFLOW");
        end
        for (int s=0;s<C;s++) begin
            count+=int'(allocated[s]);
            if (allocated[s]) begin
                outstanding+=int'(reads[s])-int'(consumed[s]);
                assert (consumed[s]<=reads[s] && reads[s]<=committed[s][0]+committed[s][1] && reads[s]<=9'(BLOCK_WORDS)) else $fatal(1,"COUNT_ORDER");
                if (32'(s)!=head) assert (reads[s]==0 && consumed[s]==0) else $fatal(1,"NONHEAD_READ");
            end else assert (!wr[s][0] && !wr[s][1]) else $fatal(1,"FREE_SLOT_ACCESS");
            assert (committed[s][0]<=9'(SPLIT_WORDS) && committed[s][1]<=9'(SUFFIX)) else $fatal(1,"COMMITTED_BOUNDS");
        end
        assert (count==int'(occupancy)) else $fatal(1,"FIFO_COUNT");
        assert (outstanding==int'(output_valid)) else $fatal(1,"OUTPUT_OWNERSHIP");
        if (out_valid) assert (allocated[output_slot] && output_slot==head && out_last==(consumed[head]==9'(BLOCK_WORDS-1))) else $fatal(1,"OUTPUT_TAG");
        for (int i=0;i<2;i++) begin
            if (active[i]) assert (allocated[owner[i]] && issued[owner[i]][i]) else $fatal(1,"OWNER_ALLOCATION");
            if (pending[i]) assert (allocated[pending_slot[i]] && !issued[pending_slot[i]][i] && !active[i]) else $fatal(1,"PENDING_ALLOCATION");
            if (rsp_valid[i]) assert (active[i] && rsp_ready[i]) else $fatal(1,"UNSOLICITED_RESPONSE");
            if (rsp_valid[i] && rsp_ready[i]) assert (rsp_last[i]==(received[i]+9'd1==length[i])) else $fatal(1,"RESPONSE_LAST");
            if (retire) assert (!(active[i] && owner[i]==head) && !(pending[i] && pending_slot[i]==head)) else $fatal(1,"PREMATURE_FREE_OWNER");
        end
        if (read_fire) assert (readable) else $fatal(1,"INVALID_READ");
        if (retire) assert (reads[head]==9'(BLOCK_WORDS) && committed[head][0]+committed[head][1]==9'(BLOCK_WORDS)) else $fatal(1,"PREMATURE_FREE");
    end
    // synthesis translate_on
endmodule
