#include "adjacencyMatGen.h"
#include "skeletonConfigs.h"

namespace AdjMatGen {
using namespace std;
Matrix generateLowerTriangularMatrix(uint32_t size, double density) {
    Matrix matrix(size, vector<uint32_t>(size, 0));
    srand(time(nullptr));
    for (uint32_t i = 0; i < size; ++i) {
        for (uint32_t j = 0; j < i; ++j) {
            if (i != j && (rand() / (double)RAND_MAX) < density) {
                matrix[i][j] = rand() % MAX_OUTBOUND_TO_SAME_NODE + 1;
            }
        }
    }
    return matrix;
}

void printMatrix(const Matrix& matrix) {
    cout << "Lower Triangular Adjacency Matrix:\n";
    for (const auto& row : matrix) {
        for (uint32_t val : row) {
            cout << val << " ";
        }
        cout << endl;
    }
}

void generateDOTFile(const Matrix& matrix, const string& filename) {
    ofstream file(filename);
    if (!file) {
        cerr << "Error opening file for writing." << endl;
        return;
    }

    file << "digraph G {\n";

    uint32_t size = matrix.size();
    for (uint32_t i = 0; i < size; ++i) {
        for (uint32_t j = 0; j < i; ++j) {
            for( uint32_t k = 0; k < matrix[i][j]; ++k)
                file << "    " << i << " -> " << j << ";\n";
        }
    }

    file << "}\n";
    file.close();

    cout << "DOT file '" << filename << "' generated successfully.\n";
}

} // namespace adjMatGen