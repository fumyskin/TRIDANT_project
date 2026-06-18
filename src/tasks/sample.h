#pragma once
#include <stdint.h>

// -- TRIDANT wire contract --
// single shared layout between firmware (this file) and the Python
// bridge (protocol.py: struct '<fffHB'. 
// ESP32 C6 is little-endian!!
// keep both sides in lockstep

// WARNING: THE FOLLOWING LINES MUST NOT BE CHANGED: THEY ARE NECESSARY TO LEAVE THE COMPILER EXACTLY UNTOUCHED
// #pragma pack(push, 1) saves whathever the current compiler alignment is,
// and change the alignment to 1 byte
#pragma pack(push, 1)
struct Sample{

    //define struct (will have 0 padding bytes)
    float phi_deg;
    float theta_deg;
    float elev_deg;
    uint16_t mv;
    uint8_t acc;
};
#pragma pack(pop) // RESTORE the compiler alignment to whathever it was before step 1

static_assert(sizeof(Sample) == 15, "Sample must be 15 packed bytes");
