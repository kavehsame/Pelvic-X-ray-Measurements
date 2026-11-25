# Restore build assets into the complete Slicer module. Installed users receive
# the same verified files in the extension bundle.
function(pxm_resolve_asset directory url name expected)
  set(asset "${directory}/${name}")
  file(MAKE_DIRECTORY "${directory}")
  file(LOCK "${CMAKE_CURRENT_BINARY_DIR}/pxm-${name}.lock" GUARD FUNCTION TIMEOUT 180)
  if(NOT EXISTS "${asset}")
    if(NOT url MATCHES "^https://github[.]com/[^/]+/[^/]+/releases/download/[^/]+$")
      message(FATAL_ERROR "Missing release URL for ${name}")
    endif()
    file(DOWNLOAD "${url}/${name}" "${asset}.download" TLS_VERIFY ON STATUS status TIMEOUT 180)
    list(GET status 0 error)
    if(NOT error EQUAL 0)
      file(REMOVE "${asset}.download")
      message(FATAL_ERROR "Could not download ${name}: ${status}")
    endif()
    file(SHA256 "${asset}.download" actual)
    if(NOT actual STREQUAL expected)
      file(REMOVE "${asset}.download")
      message(FATAL_ERROR "Downloaded asset checksum mismatch: ${name}")
    endif()
    file(RENAME "${asset}.download" "${asset}")
  else()
    file(SHA256 "${asset}" actual)
    if(NOT actual STREQUAL expected)
      message(FATAL_ERROR "Installed asset checksum mismatch: ${name}")
    endif()
  endif()
endfunction()

set(resources "${CMAKE_CURRENT_LIST_DIR}/PelvicXrayMeasurements/Resources")
pxm_resolve_asset("${resources}/AutoPlacement" "${PELVIC_MODEL_BASE_URL}" auto_point_model.json
  0884740f04ab921995de9ae73cb116a92273a5f782b7ff7b74d3a420ef23550e)
pxm_resolve_asset("${resources}/AutoPlacement" "${PELVIC_MODEL_BASE_URL}" auto_point_image_model.npz
  b1e0dcc0bc7be8bbd4af9d1510ef955fc469adea15eed665d645a6da1a699ebc)
pxm_resolve_asset("${resources}" "${PELVIC_IMPLANT_BASE_URL}" planning_templates.json
  87c80343c612de592103e968c7e96d078f5efc675d57590ebd598372294fa771)
pxm_resolve_asset("${resources}" "${PELVIC_IMPLANT_BASE_URL}" planning_artwork.zip
  b4284a15497b9a9a26451ae98c6080e61c50784fe5a8809f3aa9263be9c9d649)
