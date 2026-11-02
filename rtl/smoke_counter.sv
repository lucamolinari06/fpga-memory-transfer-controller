module smoke_counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       enable,
    output logic [7:0] count
);
    timeunit 1ns;
    timeprecision 1ps;
    always_ff @(posedge clk) begin
        if (rst) count <= 8'd0;
        else if (enable) count <= count + 8'd1;
    end
endmodule
