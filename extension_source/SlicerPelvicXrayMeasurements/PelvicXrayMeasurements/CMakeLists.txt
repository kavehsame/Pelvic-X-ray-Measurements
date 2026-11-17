set(MODULE_NAME PelvicXrayMeasurements)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  PelvicXrayMeasurementsLib/__init__.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsCalculations.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsAutoPlacement.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsCaseExport.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsCaseWorkflow.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsConstants.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsFormatting.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsGeometry.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsImageExport.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsNodeSpecs.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsResults.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsScene.py
  PelvicXrayMeasurementsLib/PelvicXrayMeasurementsWorkflow.py
)

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/${MODULE_NAME}.svg
  Resources/Icons/${MODULE_NAME}.png
  Resources/morphology_parameters_pothong_2023.png
  Resources/AutoPlacement/auto_point_model.json
  Resources/AutoPlacement/auto_point_image_model.npz
)

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
)
