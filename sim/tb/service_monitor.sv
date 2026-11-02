// Independent public-channel accounting; fixture data is not consulted.
module service_monitor (
    input logic clk, rst,
    input int unsigned profile,
    input longint unsigned epoch,
    input logic [1:0] req_valid, req_ready, rsp_valid, rsp_ready, rsp_last, grant,
    input logic [3:0] reserved,
    input logic [8:0] req_words[2],
    input logic [31:0] req_base[2], rsp_data[2],
    input int unsigned latency[2], interval_cycles[2]
);
    timeunit 1ns; timeprecision 1ps;
    bit owner[2], stalled[2];
    int unsigned count[2], total[2], base[2];
    longint accepted[2], last_response[2], transported[2], returned[2];
    logic [31:0] saved_data[2];
    bit saved_last[2];
    function automatic logic [31:0] expected(input int unsigned address);
        return 32'(64'(address)*64'h9e3779b1+64'ha5a55a5a);
    endfunction
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            for (int i=0;i<2;i++) begin
                owner[i]=0; stalled[i]=0; count[i]=0; total[i]=0; base[i]=0;
                accepted[i]=0; last_response[i]=-1; transported[i]=0; returned[i]=0;
                saved_data[i]=0; saved_last[i]=0;
            end
        end else begin
            if (profile==3) assert (!(grant==3) && !(reserved[3] && |grant))
                else $fatal(1,"MON_SHARED_CAPACITY");
            assert (!(grant[0] && reserved[0]) && !(grant[1] && (reserved[1] || reserved[2])))
                else $fatal(1,"MON_RESERVED_GRANT");
            for (int i=0;i<2;i++) begin
                assert (transported[i]-returned[i]==64'(rsp_valid[i])) else $fatal(1,"MON_CONSERVATION");
                if (stalled[i]) assert (rsp_valid[i] && rsp_data[i]==saved_data[i] && rsp_last[i]==saved_last[i])
                    else $fatal(1,"MON_RESPONSE_STABILITY");
                stalled[i]=rsp_valid[i] && !rsp_ready[i]; saved_data[i]=rsp_data[i]; saved_last[i]=rsp_last[i];
                if (req_valid[i] && req_ready[i]) begin
                    assert (!owner[i]) else $fatal(1,"MON_OUTSTANDING");
                    owner[i]=1; count[i]=0; total[i]=int'(req_words[i]); base[i]=req_base[i];
                    accepted[i]=longint'(epoch); last_response[i]=-1;
                end
                if (rsp_valid[i]) begin
                    assert (owner[i]) else $fatal(1,"MON_UNSOLICITED");
                    assert (rsp_data[i]==expected(base[i]+count[i])) else $fatal(1,"MON_DATA");
                    assert (rsp_last[i]==(count[i]+1==total[i])) else $fatal(1,"MON_LAST");
                end
                if (rsp_valid[i] && rsp_ready[i]) begin
                    count[i]++; returned[i]++; last_response[i]=longint'(epoch);
                    if (rsp_last[i]) owner[i]=0;
                end
                if (grant[i]) begin
                    assert (owner[i] && (!rsp_valid[i] || (rsp_ready[i] && !rsp_last[i])))
                        else $fatal(1,"MON_GRANT_OWNERSHIP");
                    assert (longint'(epoch)>=accepted[i]+64'(latency[i])-1 &&
                        (last_response[i]<0 || longint'(epoch)>=last_response[i]+64'(interval_cycles[i])-1))
                        else $fatal(1,"MON_GRANT_EARLY");
                    transported[i]++;
                end
            end
        end
    end
    /* verilator lint_on BLKSEQ */
endmodule
