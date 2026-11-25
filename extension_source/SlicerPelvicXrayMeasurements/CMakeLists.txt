cmake_minimum_required(VERSION 3.16.3...3.28 FATAL_ERROR)

project(PelvicXrayMeasurements)

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

set(EXTENSION_HOMEPAGE "https://github.com/kavehsame/Pelvic-X-ray-Measurements")
set(EXTENSION_CATEGORY "Orthopaedics")
set(EXTENSION_CONTRIBUTORS "Developed by: Kaveh Same, MD, MPH, PhD Candidate, Michael Ogon Laboratory for Orthopedic Research, Orthopedic Hospital Speising, Vienna, Austria;In collaboration with: ImageBiopsy Lab GmbH, Vienna, Austria;Code backbone created by: Codex, OpenAI, California, USA")
set(EXTENSION_DESCRIPTION "Research tool for editable, calibrated pelvic radiograph measurements, including bilateral landmarks, fitted geometry, Smart Point Placement and scene/CSV/image export. Research use only; not a medical device or intended for clinical decisions.")
set(EXTENSION_ICONURL "")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA")

# The publication exporter generates real repository/raw-asset URLs here.
# Empty metadata is reported as unready; never substitute Slicer's own homepage.
include(${CMAKE_CURRENT_SOURCE_DIR}/Publication.cmake OPTIONAL)
include(${CMAKE_CURRENT_SOURCE_DIR}/ResolveModels.cmake)

add_subdirectory(PelvicXrayMeasurements)

# Ship executable verification tooling with the Extensions Manager package too.
install(DIRECTORY Testing/ DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}/PelvicXrayMeasurementsVerification/Testing
  PATTERN "__pycache__" EXCLUDE PATTERN ".pytest_cache" EXCLUDE PATTERN "test_runs" EXCLUDE)
install(FILES README.md documentation.md overlay-standard.md overlay.schema.json overlay-example.json
  LICENSE.txt NOTICE.md CREDITS.md THIRD_PARTY.md CITATION.cff DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}/PelvicXrayMeasurementsVerification)
install(FILES PelvicXrayMeasurements/Resources/implant-overlays.html
  DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}/PelvicXrayMeasurementsVerification/PelvicXrayMeasurements/Resources)

include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
