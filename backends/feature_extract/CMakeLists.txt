set(FEATURE_EXTRACT_SRCS
    p4feature.cpp
    options.cpp
    main.cpp
    p4feature_extractor.cpp
)


# p4feature-extract
add_executable(p4feature-extract ${FEATURE_EXTRACT_SRCS})
target_link_libraries(p4feature-extract ${P4C_LIBRARIES} ${P4C_LIB_DEPS})
add_dependencies(p4feature-extract frontend)

add_custom_target(
  linkp4feature_extract # Add some convenience links for invoking it.
  COMMAND ${CMAKE_COMMAND} -E create_symlink ${CMAKE_CURRENT_BINARY_DIR}/p4feature-extract
          ${CMAKE_BINARY_DIR}/p4feature-extract
)

add_dependencies(p4feature-extract linkp4feature_extract)