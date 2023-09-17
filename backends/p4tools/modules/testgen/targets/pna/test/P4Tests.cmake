# General test utilities.
include(${P4TOOLS_SOURCE_DIR}/cmake/TestUtils.cmake)
# This file defines how we write the tests we generate.
include(${CMAKE_CURRENT_LIST_DIR}/TestTemplate.cmake)

#############################################################################
# TEST PROGRAMS
#############################################################################
# TODO: Currently, for developing purpose, we only use one test program.
set(PNA_SEARCH_PATTERNS "include.*dpdk/pna.p4" "small_sample")
set(
  P4TESTS_FOR_PNA "${P4C_SOURCE_DIR}/testdata/p4_16_samples/*.p4"
)
p4c_find_tests("${P4TESTS_FOR_PNA}" PNA_TESTS INCLUDE "${PNA_SEARCH_PATTERNS}" EXCLUDE "")


# Custom PNA tests, not used yet.
set(TESTGEN_PNA_P416_TESTS "${CMAKE_CURRENT_LIST_DIR}/p4-programs/*.p4")
p4c_find_tests("${TESTGEN_PNA_P416_TESTS}" CUSTOM_PNA_TESTS INCLUDE "${PNA_SEARCH_PATTERNS}" EXCLUDE "")

# Add PNA tests from P4C and from testgen/test/p4-programs/pna
set(P4C_PNA_TEST_SUITES_P416 ${PNA_TESTS} ${CUSTOM_PNA_TESTS})


#############################################################################
# TEST SUITES
#############################################################################
option(P4TOOLS_TESTGEN_PNA_TEST_METADATA "Run tests on the Metadata test back end" ON)

# check for infrap4d
find_program (INFRAP4D infrap4d
        PATHS $ENV{IPDK_RECIPE} )
# SDE_INSTALL is the path to the dpdk-target install directory
set(DPDK_ENV_SETUP TRUE AND INFRAP4D AND DEFINED ENV{SDE_INSTALL})
option(P4TOOLS_TESTGEN_PNA_TEST_PTF "Run tests on the PTF test back end" DPDK_ENV_SETUP)

# Test settings.
set(EXTRA_OPTS "--strict --print-traces --seed 1000 --max-tests 10 ")

# Metadata
# TODO: I am not sure why setting OFF does not prevent the test from running. So just comment it out.
#if(P4TOOLS_TESTGEN_PNA_TEST_METADATA)
#  p4tools_add_tests(
#    TESTS "${P4C_PNA_TEST_SUITES_P416}"
#    TAG "testgen-p4c-pna-metadata" DRIVER ${P4TESTGEN_DRIVER}
#    TARGET "dpdk" ARCH "pna" TEST_ARGS "--test-backend METADATA ${EXTRA_OPTS} "
#  )
#  include(${CMAKE_CURRENT_LIST_DIR}/PNAMetadataXfail.cmake)
#endif()

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
  # We might exclude some of the tests for PTF, so use another variable.
  set (P4C_PNA_TEST_SUITES_P416_PTF ${P4C_PNA_TEST_SUITES_P416})
  # Currently, the test back end only support ports 0-8 AT LEAST IN BMV2.
  # TODO: Support the full range of ports.
  # Note: we have a problem on using --port-ranges 0:8, which cause frontend issues.
  # DPDK SWX does not support too short pkts, so we start from 8
  p4tools_add_tests(
          TESTS "${P4C_PNA_TEST_SUITES_P416_PTF}"
          TAG "testgen-p4c-pna-ptf" DRIVER ${P4TESTGEN_DRIVER}
          TARGET "dpdk" ARCH "pna" P416_PTF TEST_ARGS "--test-backend PTF --packet-size-range 0:12000 ${EXTRA_OPTS} "
  )
  # include(${CMAKE_CURRENT_LIST_DIR}/PNAPTFXfail.cmake)  // For future use maybe
endif()
