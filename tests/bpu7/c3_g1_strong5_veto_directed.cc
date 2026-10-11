#include <cassert>
#include <iostream>
#include "cpu/pred/little_c3_strong5_veto.hh"
using gem5::branch_prediction::c3G1Strong5Veto;
int main() {
    unsigned count=0;
    for (int on=0;on<2;++on) for (int proposal=0;proposal<2;++proposal)
    for (int strong=0;strong<2;++strong) for (unsigned strength=0;strength<8;++strength) {
        const bool veto = c3G1Strong5Veto(on,proposal,strong,strength);
        assert(veto == (on && proposal && strong && strength==5));
        count+=veto;
    }
    assert(count == 1);
    std::cout << "P3_STRONG5_VETO_PREDICATE=PASS; M1=NOT_IMPLEMENTED\n";
}
