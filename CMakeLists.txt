cmake_minimum_required(VERSION 3.16.3...3.28 FATAL_ERROR)
project(PelvicXrayMeasurements)

# Slicer builds only the complete extension. The web application has its own build.
add_subdirectory(extension_source/SlicerPelvicXrayMeasurements)
