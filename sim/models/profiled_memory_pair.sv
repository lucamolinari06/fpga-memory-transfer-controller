// Simulation-only ordered paths with one descriptor and one holding word each.
// All deadlines refer to service edges; response handshake is at least grant+1.
module profiled_memory_pair (
    input logic clk, rst,
    input int unsigned profile,
    input int unsigned latency[2], interval_cycles[2], burst_words[2], burst_gap[2], cooldown_cycles[2],
    input int unsigned accept_period[2], accept_cycles[2],
    input logic [1:0] req_valid,
    output logic [1:0] req_ready,
    input logic [31:0] req_base[2],
    input logic [8:0] req_words[2],
    output logic [1:0] rsp_valid,
    input logic [1:0] rsp_ready,
    output logic [31:0] rsp_data[2],
    output logic [1:0] rsp_last,
    output logic [1:0] grant,
    output logic [1:0] eligible,
    output logic [3:0] reserved,
    output longint unsigned epoch,
    output longint unsigned row_hits, row_closed, row_conflicts,
    output longint unsigned grants[2], responses[2], maintenance_starts
);
    timeunit 1ns; timeprecision 1ps;
    logic [31:0] fixture[65536];
    string path;
    int unsigned jitter[2];
    logic [1:0] owned, held;
    int unsigned base[2], length[2], next_word[2];
    longint unsigned deadline[2], ready_at[2];
    logic [31:0] hold_data[2];
    logic [1:0] hold_last;
    bit prefer_b, was_maintenance;
    bit row_valid[4];
    int unsigned row_tag[4];
    bit setup_active;
    longint unsigned setup_end;
    logic [1:0] setup_bank;
    int unsigned setup_row, setup_kind;
    // Combinational candidates include an accepted descriptor and a consumed held beat.
    int unsigned candidate_base[2], candidate_length[2], candidate_word[2], chunk[2];
    longint unsigned candidate_deadline[2];
    logic [1:0] candidate, timing_ready;
    int unsigned address_b, row_b;
    logic [1:0] bank_b;
    bit row_ok, start_setup, boundary_b;
    timing_calendar calendar(.*);
    initial begin
        if (!$value$plusargs("dataset=%s",path)) $fatal(1,"DATASET_REQUIRED");
        $readmemh(path,fixture);
    end
    always_comb begin
        rsp_valid = held & {2{!rst}};
        rsp_last = hold_last;
        for (int i=0;i<2;i++) begin
            rsp_data[i]=hold_data[i];
            req_ready[i]=!rst && !owned[i] && epoch>=ready_at[i]
                && epoch%64'(accept_period[i])<64'(accept_cycles[i]);
            chunk[i]=(i==1 && burst_words[i]>16) ? 16 : burst_words[i];
            candidate_base[i]=base[i]; candidate_length[i]=length[i]; candidate_word[i]=next_word[i];
            candidate_deadline[i]=deadline[i];
            candidate[i]=owned[i] && (!held[i] || (rsp_ready[i] && !hold_last[i]));
            if (held[i] && rsp_ready[i] && !hold_last[i]) begin
                candidate_deadline[i]=epoch+64'(interval_cycles[i])-1;
                if ((i==1 ? (base[i]+next_word[i])%chunk[i] : next_word[i]%chunk[i])==0)
                    candidate_deadline[i]+=64'(burst_gap[i]);
            end
            if (req_valid[i] && req_ready[i]) begin
                candidate[i]=1;
                candidate_base[i]=req_base[i]; candidate_length[i]=int'(req_words[i]); candidate_word[i]=0;
                candidate_deadline[i]=epoch+64'(latency[i])+64'(jitter[i])-1;
            end
            timing_ready[i]=candidate[i] && epoch>=candidate_deadline[i];
        end
        boundary_b=candidate_word[1]==0 || (candidate_base[1]+candidate_word[1])%chunk[1]==0;
        address_b=candidate_base[1]+candidate_word[1];
        bank_b=2'((address_b/256)%4); row_b=address_b/1024;
        row_ok=row_valid[bank_b] && row_tag[bank_b]==row_b;
        // Maintenance invalidates even completed setups waiting for a service opportunity.
        start_setup=timing_ready[1] && !row_ok && !setup_active && !reserved[2];
        eligible='0;
        eligible[0]=!rst && timing_ready[0] && !reserved[0];
        eligible[1]=!rst && timing_ready[1] && row_ok && !reserved[1] && !reserved[2];
        grant=eligible;
        if (profile==3) begin
            if (reserved[3]) grant='0;
            else if (&eligible) grant=prefer_b ? 2'b10 : 2'b01;
        end
    end
    always @(posedge clk) begin
        if (rst) begin
            owned<='0; held<='0; hold_last<='0; prefer_b<=0; was_maintenance<=0;
            setup_active<=0; setup_end<=0; setup_bank<=0; setup_row<=0; setup_kind<=0;
            row_hits<=0; row_closed<=0; row_conflicts<=0; maintenance_starts<=0;
            for (int i=0;i<4;i++) begin row_valid[i]<=0; row_tag[i]<=0; end
            for (int i=0;i<2;i++) begin
                base[i]<=0; length[i]<=0; next_word[i]<=0; deadline[i]<=0; ready_at[i]<=0;
                hold_data[i]<=0; grants[i]<=0; responses[i]<=0;
            end
        end else begin
            assert (profile>=1 && profile<=3) else $fatal(1,"PROFILE_CONFIG");
            was_maintenance<=reserved[2];
            if (reserved[2]) begin
                for (int i=0;i<4;i++) row_valid[i]<=0;
                setup_active<=0;
                if (!was_maintenance) maintenance_starts<=maintenance_starts+1;
            end else if (start_setup) begin
                setup_active<=1; setup_bank<=2'(bank_b); setup_row<=row_b;
                setup_end<=epoch+(row_valid[bank_b] ? 24 : 12)-1;
                setup_kind<=row_valid[bank_b] ? 2 : 1;
            end else if (setup_active && epoch>=setup_end) begin
                setup_active<=0; row_valid[setup_bank]<=1; row_tag[setup_bank]<=setup_row;
                if (setup_kind==1) row_closed<=row_closed+1;
                else row_conflicts<=row_conflicts+1;
            end
            // Hit counted once at a chunk's actual grant; setup completions count misses.
            if (grant[1] && boundary_b && setup_kind==0) row_hits<=row_hits+1;
            if (grant[1]) setup_kind<=0;
            if (profile==3 && |grant) prefer_b<=grant[0];
            for (int i=0;i<2;i++) begin
                assert (latency[i]>=1 && interval_cycles[i]>=1 && burst_words[i]>=1 &&
                    accept_period[i]>=1 && accept_cycles[i]>=1 && accept_cycles[i]<=accept_period[i])
                    else $fatal(1,"MEMORY_CONFIG");
                assert (grants[i]==responses[i]+64'(held[i])) else $fatal(1,"SERVICE_CONSERVATION");
                if (req_valid[i] && req_ready[i]) begin
                    assert (req_words[i]>0 && req_words[i]<=256 &&
                        64'(req_base[i])+64'(req_words[i])<=65536) else $fatal(1,"MEMORY_REQUEST_BOUNDS");
                    owned[i]<=1; base[i]<=req_base[i]; length[i]<=int'(req_words[i]); next_word[i]<=0;
                    deadline[i]<=candidate_deadline[i];
                end
                if (rsp_valid[i] && rsp_ready[i]) begin
                    held[i]<=0; responses[i]<=responses[i]+1;
                    if (rsp_last[i]) begin owned[i]<=0; ready_at[i]<=epoch+1+64'(cooldown_cycles[i]); end
                    else deadline[i]<=candidate_deadline[i];
                end
                if (grant[i]) begin
                    assert (candidate[i] && (!held[i] || rsp_ready[i])) else $fatal(1,"SERVICE_CAPACITY");
                    held[i]<=1; hold_data[i]<=fixture[candidate_base[i]+candidate_word[i]];
                    hold_last[i]<=candidate_word[i]+1==candidate_length[i];
                    next_word[i]<=candidate_word[i]+1; grants[i]<=grants[i]+1;
                end
            end
        end
    end
    for (genvar i=0;i<2;i++) begin : g_stability
        assert property (@(posedge clk) disable iff (rst)
            rsp_valid[i] && !rsp_ready[i] |=> rsp_valid[i] && $stable({rsp_data[i],rsp_last[i]}))
            else $fatal(1,"MEMORY_RESPONSE_STABILITY");
    end
endmodule
