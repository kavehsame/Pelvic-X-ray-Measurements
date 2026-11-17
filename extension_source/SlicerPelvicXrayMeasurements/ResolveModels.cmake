# Model weights stay out of Git. Source release kits contain them; fresh Slicer
# factory checkouts fetch approved, immutable release assets while building.
# Installed users never need a model download or an extra Python dependency.
set(PELVIC_MODEL_NAMES auto_point_model.json auto_point_image_model.npz)
set(PELVIC_MODEL_HASHES
  0884740f04ab921995de9ae73cb116a92273a5f782b7ff7b74d3a420ef23550e
  b1e0dcc0bc7be8bbd4af9d1510ef955fc469adea15eed665d645a6da1a699ebc)
set(_model_directory "${CMAKE_CURRENT_SOURCE_DIR}/PelvicXrayMeasurements/Resources/AutoPlacement")
foreach(_index RANGE 0 1)
  list(GET PELVIC_MODEL_NAMES ${_index} _name)
  list(GET PELVIC_MODEL_HASHES ${_index} _hash)
  set(_model "${_model_directory}/${_name}")
  if(NOT EXISTS "${_model}")
    if(NOT PELVIC_MODEL_BASE_URL MATCHES "^https://github.com/[^/]+/[^/]+/releases/download/[^/]+$")
      message(FATAL_ERROR "Missing ${_name}. Supply the model release kit or configure the approved GitHub model-release URL in Publication.cmake.")
    endif()
    file(MAKE_DIRECTORY "${_model_directory}")
    file(DOWNLOAD "${PELVIC_MODEL_BASE_URL}/${_name}" "${_model}"
      EXPECTED_HASH "SHA256=${_hash}" TLS_VERIFY ON STATUS _status)
    list(GET _status 0 _code)
    if(NOT _code EQUAL 0)
      message(FATAL_ERROR "Could not retrieve approved model ${_name}: ${_status}")
    endif()
  endif()
  file(SHA256 "${_model}" _actual)
  if(NOT _actual STREQUAL _hash)
    message(FATAL_ERROR "Model checksum mismatch: ${_name}; existing model was not replaced.")
  endif()
endforeach()
