set(P4LACPP_BE_SRCS
    p4lacpp.cpp
    options.cpp
    main.cpp
    p4feature_extractor.cpp
)


# p4lacpp
add_executable(p4lacpp ${P4LACPP_BE_SRCS})
target_link_libraries(p4lacpp ${P4C_LIBRARIES} ${P4C_LIB_DEPS})
add_dependencies(p4lacpp frontend)

add_custom_target(
  linkp4lacpp # Add some convenience links for invoking it.
  COMMAND ${CMAKE_COMMAND} -E create_symlink ${CMAKE_CURRENT_BINARY_DIR}/p4lacpp
          ${CMAKE_BINARY_DIR}/p4lacpp
)

add_dependencies(p4lacpp linkp4lacpp)