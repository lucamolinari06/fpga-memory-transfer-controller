// Fixed 16-word record: {id, key, 14 unsigned payload words}.
// A rejected record may end at its key or retain its full eager payload.
module record_reduce (
    input logic clk, rst,
    input logic [31:0] threshold,
    input logic in_valid,
    output logic in_ready,
    input logic [31:0] in_data,
    input logic in_last,
    output logic result_valid,
    input logic result_ready,
    output logic [31:0] result_id,
    output logic result_selected,
    output logic [63:0] result_sum
);
    timeunit 1ns; timeprecision 1ps;
    logic [3:0] word_index;
    logic [31:0] record_id;
    logic selected, held_valid;
    logic [63:0] sum;
    logic accept;

    assign result_valid = !rst && held_valid;
    assign in_ready = !rst && (!held_valid || result_ready);
    assign accept = in_valid && in_ready;

    always_ff @(posedge clk) begin
        if (rst) begin
            word_index <= 0;
            record_id <= 0;
            selected <= 0;
            sum <= 0;
            held_valid <= 0;
            result_id <= 0;
            result_selected <= 0;
            result_sum <= 0;
        end else begin
            if (held_valid && result_ready) held_valid <= 0;
            if (accept) begin
                if (word_index == 0) begin
                    record_id <= in_data;
                    selected <= 0;
                    sum <= 0;
                    word_index <= 1;
                end else if (word_index == 1) begin
                    selected <= in_data < threshold;
                    if (in_last) begin
                        result_id <= record_id;
                        result_selected <= 0;
                        result_sum <= 0;
                        held_valid <= 1;
                        word_index <= 0;
                    end else word_index <= 2;
                end else if (word_index == 15) begin
                    result_id <= record_id;
                    result_selected <= selected;
                    result_sum <= selected ? sum + {32'b0,in_data} : 64'b0;
                    held_valid <= 1;
                    word_index <= 0;
                end else begin
                    if (selected) sum <= sum + {32'b0,in_data};
                    word_index <= word_index + 1'b1;
                end
            end
        end
    end

    // synthesis translate_off
    logic input_stalled, result_stalled;
    logic [32:0] held_input;
    logic [96:0] held_result;
    always @(posedge clk) begin
        if (rst) begin
            input_stalled <= 0;
            result_stalled <= 0;
            held_input <= 0;
            held_result <= 0;
        end else begin
            if (input_stalled)
                assert (in_valid && {in_data,in_last} == held_input)
                    else $fatal(1, "REDUCE_INPUT_UNSTABLE");
            if (result_stalled)
                assert (result_valid && {result_id,result_selected,result_sum} == held_result)
                    else $fatal(1, "REDUCE_RESULT_UNSTABLE");
            input_stalled <= in_valid && !in_ready;
            result_stalled <= result_valid && !result_ready;
            held_input <= {in_data,in_last};
            held_result <= {result_id,result_selected,result_sum};
            if (accept) begin
                if (word_index == 1 && in_last)
                    assert (in_data >= threshold) else $fatal(1, "REDUCE_SHORT_SELECTED");
                else
                    assert (in_last == (word_index == 15)) else $fatal(1, "REDUCE_RECORD_LENGTH");
            end
        end
    end
    // synthesis translate_on
endmodule
