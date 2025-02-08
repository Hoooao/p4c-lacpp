#include "adjacencyMatGen.h"
#include "skeleton.h"
// just for some testing..
int main() {
    uint32_t size = 5;
    double density = 0.6; 
    std::vector<std::vector<uint32_t>> matrix = AdjMatGen::generateLowerTriangularMatrix(size, density);
    AdjMatGen::printMatrix(matrix);

    std::string filename = "graph.dot";
    AdjMatGen::generateDOTFile(matrix, filename);

    return 0;
}