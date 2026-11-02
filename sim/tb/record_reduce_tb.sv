module record_reduce_tb;
    timeunit 1ns; timeprecision 1ps;
    logic clk;
    initial begin
        clk = 0;
        forever #5 clk = !clk;
    end
    logic rst = 1;
    logic in_valid = 0, in_ready, in_last = 0;
    logic [31:0] in_data = 0;
    logic result_valid, result_ready;
    logic [31:0] result_id;
    logic result_selected;
    logic [63:0] result_sum;
    int unsigned cycle, checked, epoch = 0;
    int unsigned fault = 0;
    typedef struct packed {
        logic [31:0] id;
        logic selected;
        logic [63:0] sum;
    } expected_t;
    expected_t expected[4];

    record_reduce dut (
        .clk, .rst, .threshold(32'd50), .in_valid, .in_ready, .in_data, .in_last,
        .result_valid, .result_ready, .result_id, .result_selected, .result_sum
    );
    assign result_ready = !rst && (cycle % 11 >= 4);

    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            cycle = 0;
            checked = 0;
        end else begin
            cycle++;
            assert (cycle < 1000) else $fatal(1, "REDUCE_TEST_TIMEOUT");
            if (result_valid && result_ready) begin
                assert (checked < (epoch == 0 ? 4 : 1)) else $fatal(1, "REDUCE_TEST_EXTRA");
                assert ({result_id,result_selected,result_sum} == expected[checked])
                    else $fatal(1, "REDUCE_TEST_RESULT id=%0d selected=%0d sum=%0d",
                                result_id,result_selected,result_sum);
                checked++;
            end
        end
    end
    /* verilator lint_on BLKSEQ */

    task automatic word(input logic [31:0] data, input logic last);
        @(negedge clk);
        in_valid = 1;
        in_data = data;
        in_last = last;
        do @(posedge clk); while (!in_ready);
        @(negedge clk);
        in_valid = 0;
    endtask

    initial begin
        if ($value$plusargs("fault=%d",fault)) begin end
        expected[0] = '{32'd11,1'b1,64'd60129542130};
        expected[1] = '{32'd22,1'b0,64'd0};
        expected[2] = '{32'd33,1'b0,64'd0};
        expected[3] = '{32'd44,1'b1,64'd105};
        repeat (3) @(negedge clk);
        rst = 0;
        if (fault == 1) begin
            word(11,0);
            word(20,1);
            $fatal(1, "REDUCE_TEST_FAULT_MISSED");
        end
        if (fault == 2) begin
            word(11,1);
            $fatal(1, "REDUCE_TEST_FAULT_MISSED");
        end
        word(11,0); word(20,0);
        for (int i=0;i<14;i++) word(32'hffffffff,i==13);
        word(22,0); word(80,0);
        for (int i=0;i<14;i++) word(32'(i),i==13);
        word(33,0); word(50,1);
        word(44,0); word(0,0);
        for (int i=1;i<=14;i++) word(32'(i),i==14);
        wait (checked == 4);
        // Reset cancels a partially accumulated record, then a fresh record is checked.
        word(55,0); word(0,0); word(99,0); word(99,0);
        @(negedge clk);
        rst = 1;
        epoch = 1;
        expected[0] = '{32'd66,1'b1,64'd105};
        repeat (3) @(negedge clk);
        rst = 0;
        word(66,0); word(1,0);
        for (int i=1;i<=14;i++) word(32'(i),i==14);
        wait (checked == 1);
        repeat (20) @(negedge clk);
        $display("PASS record reducer: full/short rejects, 64-bit max sum, stalls, partial reset");
        $finish;
    end
endmodule
