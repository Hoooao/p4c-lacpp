// The lacpp_addons module serves as a collection of additional functionalities and
// or instrumentations used for bf-p4c required by lacpp.
// We try best not to be too intrusive to the original code.
// Thus every modification should be made as a module that can be traced to here!
#ifndef BF_P4C_LACPP_ADDONS_H_
#define BF_P4C_LACPP_ADDONS_H_

#include "ir/ir.h"
#include "ir/visitor.h"
#include <chrono>
namespace BFN::LacppAddons {

    class PerfTimer: public Inspector {
    public:
        PerfTimer(): started(false){}
        void start();
        void stop();
        void print();
        void reset();
        bool preorder(const IR::Node *) override;
        // bool preorder(const IR::P4Program *program) override;
    private:    
        bool started = false;
        std::chrono::high_resolution_clock::time_point start_time;
        std::chrono::high_resolution_clock::time_point end_time;
        std::chrono::duration<double> elapsed_time;
        
    };


}  // namespace BFN::LacppAddons

#endif /* BF_P4C_LACPP_ADDONS_H_ */