# aes sky130hd 23539 insts
source "helpers.tcl"
source "flow_helpers.tcl"
source "sky130hd/sky130hd.vars"

set design "aes"
set top_module "aes_cipher_top"
set synth_verilog "aes_sky130hd.v"
set sdc_file "aes_sky130hd.sdc"
set die_size 2000
set die_area "0 0 $die_size $die_size"
set core_area "30 30 [expr {$die_size - 230}] [expr {$die_size - 230}]"

set slew_margin 20

include -echo "flow.tcl"
