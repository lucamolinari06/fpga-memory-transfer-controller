module smoke_tb;
    timeunit 1ns;
    timeprecision 1ps;
    logic clk;
    logic rst;
    logic enable;
    logic [7:0] count;
    smoke_counter dut (.*);
    initial clk = 0;
    always #5 clk <= ~clk;

    // Drive on falling edges and sample after rising-edge updates.
    task automatic step(input bit reset_value, input bit enable_value,
                        input logic [7:0] expected);
        @(negedge clk);
        rst = reset_value;
        enable = enable_value;
        @(posedge clk);
        #1;
        if (count !== expected)
            $fatal(1, "count=%0d expected=%0d", count, expected);
    endtask

    initial begin
        rst = 1;
        enable = 0;
        step(1, 0, 0);
        step(0, 1, 1);
        step(0, 1, 2);
        step(0, 0, 2);
        step(1, 1, 0);
        step(0, 1, 1);
        $display("PASS smoke: reset, increment, hold, active reset");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "smoke timeout");
    end
endmodule
