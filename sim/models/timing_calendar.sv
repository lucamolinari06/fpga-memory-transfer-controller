// Finite, externally generated schedule. Header is a lossless periodic-event encoding;
// jitter samples are explicitly stored for every 16-edge interval. No DUT inputs.
module timing_calendar (
    input logic clk, rst,
    input int unsigned profile,
    output longint unsigned epoch,
    output int unsigned jitter[2],
    output logic [3:0] reserved // A, B, B maintenance, shared return
);
    timeunit 1ns; timeprecision 1ps;
    int unsigned limit, periods[4], durations[4], phases[4];
    int unsigned samples[4194304];
    int file, status, value;
    string path;
    initial begin
        if (!$value$plusargs("calendar=%s",path)) $fatal(1,"TRACE_REQUIRED");
        file=$fopen(path,"r");
        if (file==0) $fatal(1,"TRACE_OPEN");
        status=$fscanf(file,"%d",limit);
        if (status!=1 || limit<1 || limit>67108864) $fatal(1,"TRACE_FORMAT");
        for (int i=0;i<4;i++) begin
            status=$fscanf(file,"%d %d %d",periods[i],durations[i],phases[i]);
            if (status!=3 || periods[i]<1 || durations[i]>=periods[i] || phases[i]>=periods[i])
                $fatal(1,"TRACE_FORMAT");
        end
        for (int i=0;i<int'((limit+15)/16);i++) begin
            status=$fscanf(file,"%h",value);
            if (status!=1 || value<0 || value>31 || (value & 3)>2) $fatal(1,"TRACE_FORMAT");
            samples[i]=value;
        end
        status=$fscanf(file,"%h",value);
        if (status!=-1) $fatal(1,"TRACE_FORMAT_EXTRA");
        $fclose(file);
    end
    always_comb begin
        jitter[0]=0; jitter[1]=0; reserved='0;
        if (epoch<64'(limit)) begin
            jitter[0]=samples[int'(epoch/16)] & 3;
            jitter[1]=(samples[int'(epoch/16)] >> 2) & 7;
            if (profile>=2) for (int i=0;i<4;i++)
                reserved[i]=((epoch+64'(periods[i])-64'(phases[i]))%64'(periods[i]))<64'(durations[i]);
        end
    end
    always @(posedge clk) begin
        if (rst) epoch<=0;
        else begin
            assert (epoch<64'(limit)) else $fatal(1,"TRACE_EXHAUSTED");
            epoch<=epoch+1;
        end
    end
endmodule
