* Synthetic generic-name two-stage OTA for NetlistLabel.
* Every instance is XM*/XC* with no semantic token in the name.
* This is a test fixture, not a working sky130 design.
*
.subckt ota_generic inp inn out vdd vss nbias pbias
*.PININFO inp:I inn:I out:O vdd:I vss:I nbias:I pbias:I
XM1 n1 inp tail vss sky130_fd_pr__nfet_01v8 L=0.5 W=2 nf=1 m=1
XM2 n2 inn tail vss sky130_fd_pr__nfet_01v8 L=0.5 W=2 nf=1 m=1
XM3 tail nbias vss vss sky130_fd_pr__nfet_01v8 L=1 W=4 nf=1 m=1
XM4 n1 n1 vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=2 nf=1 m=1
XM5 n2 n1 vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=2 nf=1 m=1
XM6 out n2 vss vss sky130_fd_pr__nfet_01v8 L=0.5 W=6 nf=1 m=1
XM7 out pbias vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM8 pbias pbias vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=2 nf=1 m=1
XC1 n2 out 1.5p
.ends
