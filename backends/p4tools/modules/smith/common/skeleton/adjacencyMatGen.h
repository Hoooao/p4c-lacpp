#ifndef ADJACENCY_MAT_GEN_H
#define ADJACENCY_MAT_GEN_H
#include <iostream>
#include <vector>
#include <fstream>
#include <ctime>
#include <cstdlib>
typedef std::vector<std::vector<uint32_t>> Matrix;
namespace AdjMatGen {
    Matrix generateLowerTriangularMatrix(uint32_t size, double density = 0.5);
    void printMatrix(const Matrix& matrix);
    void generateDOTFile(const Matrix& matrix, const std::string& filename);
}
#endif // ADJACENCY_MAT_GEN_H