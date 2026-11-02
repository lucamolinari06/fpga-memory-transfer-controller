module profiled_memory_tb;
    timeunit 1ns; timeprecision 1ps;
    logic clk, rst;
    initial begin clk=0;rst=1;end
    always #5 clk<=~clk;
    int unsigned profile=3;
    int unsigned latency[2], interval_cycles[2], burst_words[2], burst_gap[2], cooldown_cycles[2];
    int unsigned accept_period[2], accept_cycles[2];
    logic [1:0] req_valid, req_ready, rsp_valid, rsp_ready, rsp_last, grant, eligible;
    logic [31:0] req_base[2], rsp_data[2];
    logic [8:0] req_words[2];
    logic [3:0] reserved;
    longint unsigned epoch,row_hits,row_closed,row_conflicts,grants[2],responses[2],maintenance_starts;
    logic [1:0] checked_valid, checked_last, checked_grant;
    logic [31:0] checked_data[2];
    int unsigned scenario, fault, reset_generation;
    int file;
    string path;
    bit injected, armed;
    profiled_memory_pair memory_pair(.*);
    service_monitor monitor(.rsp_valid(checked_valid),.rsp_last(checked_last),.rsp_data(checked_data),
        .grant(checked_grant),.*);
    always_comb begin
        checked_valid=rsp_valid; checked_last=rsp_last; checked_grant=grant;
        checked_data[0]=rsp_data[0]; checked_data[1]=rsp_data[1];
        if (fault==1 && armed && rsp_valid[0]) checked_valid[0]=0;
        if (fault==2 && armed && rsp_valid[0]) checked_data[0]=rsp_data[0]^32'd1;
        if (fault==3 && rsp_valid[0]) checked_data[0]=32'ha5a55a5a;
        if (fault==4 && rsp_valid[0]) checked_last[0]=!rsp_last[0];
        if (fault==5 && reserved[3]) checked_grant=3;
        if (fault==6 && reserved[0]) checked_grant[0]=1;
        if (fault==7 && reset_generation>1 && epoch==0) checked_valid[0]=1;
        if (fault==8 && rsp_valid[0] && rsp_ready[0]) checked_valid[0]=0;
    end
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin armed=0; injected=0; end
        else begin
            if (rsp_valid[0] && !rsp_ready[0]) armed=1;
            if (fault!=0 && (checked_valid!=rsp_valid || checked_last!=rsp_last || checked_grant!=grant ||
                            checked_data[0]!=rsp_data[0])) injected=1;
            $fdisplay(file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                epoch,req_valid&req_ready,grant,rsp_valid,rsp_ready,rsp_last,rsp_data[0],rsp_data[1],reserved,
                row_hits,row_closed,row_conflicts,grants[0],grants[1],responses[0],responses[1],maintenance_starts);
        end
    end
    /* verilator lint_on BLKSEQ */
    task automatic tick(input int count);
        repeat(count) begin @(posedge clk); #1; end
    endtask
    task automatic request(input bit iface,input int addr,input logic [8:0] words);
        @(negedge clk); req_base[iface]=32'(addr);req_words[iface]=9'(words);req_valid[iface]=1;
        do begin @(posedge clk); #1; end while (!memory_pair.owned[iface]);
        @(negedge clk);req_valid[iface]=0;
    endtask
    task automatic drain;
        do begin @(posedge clk); #1; end while (memory_pair.owned!=0);
        tick(3);
    endtask
    task automatic reset_epoch;
        @(negedge clk);rst=1;reset_generation++;req_valid=0;tick(2);
        @(negedge clk);rst=0;rsp_ready=3;
    endtask
    initial begin
        req_valid=0;rsp_ready=3;scenario=0;fault=0;reset_generation=0;
        for (int i=0;i<2;i++) begin
            latency[i]=2;interval_cycles[i]=1;burst_words[i]=16;burst_gap[i]=0;cooldown_cycles[i]=0;
            accept_period[i]=1;accept_cycles[i]=1;req_base[i]=0;req_words[i]=0;
        end
        void'($value$plusargs("scenario=%d",scenario));void'($value$plusargs("fault=%d",fault));
        void'($value$plusargs("profile=%d",profile));
        if (!$value$plusargs("events=%s",path)) $fatal(1,"EVENTS_REQUIRED");
        file=$fopen(path,"w");
        $fdisplay(file,"cycle,request,grant,valid,ready,last,data_a,data_b,reserved,hits,closed,conflicts,a_grants,b_grants,a_responses,b_responses,pauses");
        reset_epoch();
        case (scenario)
          0: begin // Cold/hit/conflict, four banks, cross-row and unaligned chunks.
              request(1,0,1);drain(); request(1,16,2);drain();
              request(1,1024,1);drain();request(1,256,1);drain();
              request(1,255,3);drain();request(1,15,18);drain();request(1,1023,3);drain();
          end
          1: begin // Prime row publicly, then simultaneous requests (table normalized to their request edge).
              request(1,0,1);drain();
              @(negedge clk);req_valid=3;req_base[0]=0;req_base[1]=2;req_words[0]=2;req_words[1]=2;
              @(posedge clk);#1;@(negedge clk);req_valid=0;drain();
          end
          2: begin // Holds, including final response, across scheduled pauses.
              rsp_ready=0;
              @(negedge clk);req_valid=3;req_base[0]=100;req_base[1]=200;req_words[0]=2;req_words[1]=1;
              @(posedge clk);#1;@(negedge clk);req_valid=0;
              tick(100);@(negedge clk);rsp_ready=3;drain();
          end
          3,4,5,6,7,9: begin // Reset setup, waiting service, one/both holds, one accepted.
              rsp_ready=0;
              if (scenario==7) request(0,300,2);
              else begin
                  @(negedge clk);req_valid=3;req_base[0]=300;req_base[1]=400;req_words[0]=2;req_words[1]=2;
                  @(posedge clk);#1;@(negedge clk);req_valid=0;
              end
              if (scenario==3) tick(3);
              if (scenario==4) tick(1);
              if (scenario==5) tick(8);
              if (scenario==6) tick(80);
              if (scenario==9) tick(30);
              case(scenario)
                3: assert(memory_pair.setup_active) else $fatal(1,"WITNESS_SETUP");
                4: assert(memory_pair.owned[1] && !rsp_valid[1]) else $fatal(1,"WITNESS_WAIT");
                5: assert(rsp_valid==1) else $fatal(1,"WITNESS_ONE_HOLD");
                6: assert(rsp_valid==3) else $fatal(1,"WITNESS_TWO_HOLDS");
                7: assert(memory_pair.owned==1) else $fatal(1,"WITNESS_ONE_ACCEPT");
                9: assert(reserved[2]) else $fatal(1,"WITNESS_PAUSE");
                default: $fatal(1,"WITNESS_CASE");
              endcase
              reset_epoch();request(0,1000,3);drain();request(1,2048,2);drain();
          end
          8: begin // Minimum latency and consecutive service on baseline.
              latency[0]=1;request(0,7,5);drain();
          end
          10: begin
              tick(20);request(1,0,1);drain();
          end
          default: $fatal(1,"TEST_SCENARIO");
        endcase
        assert (!(|eligible) && !(|rsp_valid) && grants[0]==responses[0] && grants[1]==responses[1])
            else $fatal(1,"UNIT_DRAIN");
        assert (!injected) else $fatal(1,"FAULT_UNDETECTED");
        $display("PASS profiled memory scenario=%0d rows=%0d/%0d/%0d",scenario,row_hits,row_closed,row_conflicts);
        $fclose(file);$finish;
    end
    initial begin
        if ($test$plusargs("trace")) begin $dumpfile("trace.vcd");$dumpvars(1,profiled_memory_tb);end
    end
    initial begin #100000; $fatal(1,"UNIT_TIMEOUT");end
endmodule
