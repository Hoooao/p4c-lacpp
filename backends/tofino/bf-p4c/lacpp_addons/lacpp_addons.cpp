#include "lacpp_addons.h"
#include "lib/log.h"
#include "lib/error.h"

#include <iostream>

namespace BFN::LacppAddons{
    void PerfTimer::start() {
        start_time = std::chrono::high_resolution_clock::now();
    }
    void PerfTimer::stop() {
        end_time = std::chrono::high_resolution_clock::now();
        // start, stop can be called multiple times
        elapsed_time += end_time - start_time;
    }
    void PerfTimer::print() {
        ::warning("PerfEstimate time: %f ms", std::chrono::duration<double, std::milli>(elapsed_time).count());
    }

    void PerfTimer::reset() {
        elapsed_time = std::chrono::duration<double>::zero();
    }

    bool PerfTimer::preorder(const IR::Node *) {
        if(started) {
            stop();
            print();
            started = false;
        }else{
            start();
            started = true;
        }
        return false;
    }
}