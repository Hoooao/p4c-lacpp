# General test utilities.
include(${P4TOOLS_SOURCE_DIR}/cmake/TestUtils.cmake)
# This file defines how we write the tests we generate.
include(${CMAKE_CURRENT_LIST_DIR}/TestTemplate.cmake)

#############################################################################
# TEST PROGRAMS
#############################################################################
set(PNA_SEARCH_PATTERNS "include.*pna.p4" "main")
# General PNA tests supplied by the compiler.
set(
  P4TESTS_FOR_PNA "${P4C_SOURCE_DIR}/testdata/p4_16_samples/*.p4"
)
p4c_find_tests("${P4TESTS_FOR_PNA}" PNA_TESTS INCLUDE "${PNA_SEARCH_PATTERNS}" EXCLUDE "")

# Custom PNA tests.
set(TESTGEN_PNA_P416_TESTS "${CMAKE_CURRENT_LIST_DIR}/p4-programs/*.p4")
p4c_find_tests("${TESTGEN_PNA_P416_TESTS}" CUSTOM_PNA_TESTS INCLUDE "${PNA_SEARCH_PATTERNS}" EXCLUDE "")

# Add PNA tests from P4C and from testgen/test/p4-programs/pna
set(PNA_TEST_SUITE ${PNA_TESTS} ${CUSTOM_PNA_TESTS})


#############################################################################
# TEST SUITES
#############################################################################
option(P4TOOLS_TESTGEN_PNA_TEST_METADATA "Run tests on the Metadata test back end" ON)
option(P4TOOLS_TESTGEN_PNA_TEST_PTF "Run tests on the PTF test back end" ON)
# Test settings.
set(EXTRA_OPTS "--strict --print-traces --seed 1000 --max-tests 10 ")

# Metadata
if(P4TOOLS_TESTGEN_PNA_TEST_METADATA)
  p4tools_add_tests(
    TESTS "${PNA_TEST_SUITE}"
    TAG "testgen-p4c-pna-metadata" DRIVER ${P4TESTGEN_DRIVER}
    TARGET "dpdk" ARCH "pna" TEST_ARGS "--test-backend METADATA ${EXTRA_OPTS} "
  )
  include(${CMAKE_CURRENT_LIST_DIR}/PNAMetadataXfail.cmake)
endif()

# PTF
# TODO: The PTF test back end currently does not support packet sizes over 12000 bits, so we limit
# the range (at least it is the case in Bmv2).
if(P4TOOLS_TESTGEN_PNA_TEST_PTF)
  execute_process(COMMAND bash -c "printf \"import google.rpc\nimport google.protobuf\" | python3" RESULT_VARIABLE result)
  if(result AND NOT result EQUAL 0)
    message(
            WARNING
            "Pna PTF tests are enabled, but the Python3 module 'google.rpc' can not be found. Pna PTF tests will fail."
    )
  endif()
  # Filter some programs because they have issues that are not captured with Xfails AT LEAST IN BMV2..
  set (P4C_V1_TEST_SUITES_P416_PTF ${P4C_V1_TEST_SUITES_P416})
  list(REMOVE_ITEM P4C_V1_TEST_SUITES_P416_PTF
          # A particular test (or packet?) combination leads to an infinite loop in the simple switch.
          "${P4C_SOURCE_DIR}/testdata/p4_16_samples/v1model-special-ops-bmv2.p4"
          )
  # Currently, the test back end only support ports 0-8 AT LEAST IN BMV2.
  # TODO: Support the full range of ports.
  p4tools_add_tests(
          TESTS "${P4C_V1_TEST_SUITES_P416_PTF}"
          TAG "testgen-p4c-pna-ptf" DRIVER ${P4TESTGEN_DRIVER}
          TARGET "dpdk" ARCH "pna" P416_PTF TEST_ARGS "--test-backend PTF --packet-size-range 0:12000 --port-ranges 0:8 ${EXTRA_OPTS} "
  )
  # include(${CMAKE_CURRENT_LIST_DIR}/PNAPTFXfail.cmake)  // For future use maybe
endif()


