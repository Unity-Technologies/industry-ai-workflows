# pxz API Reference

<!-- pxz-verified-version: 2026.4.0.0 -->
<!-- This marker records the SDK version the signatures below were extracted from.
     It must equal the installed pxz version. When you bump the SDK, re-extract
     this reference from the new stubs and update it. -->

Authoritative reference for the Asset Transformer (`pxz`) Python SDK, version **2026.4.0.0** (docs: <https://docs.unity.com/en-us/asset-transformer-sdk/2026.4/api/python/pxz_functions>).

**Modules covered:** `core`, `scene`, `algo`, `io`, `geom`, `view`, `material`, `polygonal`, `cad`, `raytrace`. The `unity` module is intentionally omitted (Unity-editor integration, not applicable to headless AT scripting).

> **Version note.** Signatures below are verified against the `*.pyi` type stubs shipped inside the installed `pxz` package, currently **2026.4.0.0** — the exact surface the in-process `run_python` tool executes against, and therefore the ground truth for what works. Re-extract this reference from the stubs whenever the SDK is upgraded so the marker never drifts from the installed pxz version. (The 2026.4.0.0 surface is identical to 2026.3.2.1 for every covered module.)

## Ground rules for using this reference

- **Integer handles.** All entities (occurrences, materials, images, meshes, viewers, baking sessions, and CAD BRep entities — bodies, faces, edges, curves, surfaces) are `int` ids. There is no Python `Node` / `Material` / `Image` / `cad.Body` *object* — pass and receive `int`. If a snippet uses `scene.Node` or `scene.NodeType`, it is wrong.
- **List arguments.** Most functions that operate on the scene take `occurrences: list[int]`, even for a single occurrence (`[root]`).
- **Init depends on context.** `pxz.initialize()`, `core.checkLicense`, `core.configureLicenseServer`, `core.needToken`, etc. are listed for completeness; **do not call them** from either a UPA custom-script action or the in-process `run_python` tool — both hand you an already-initialized, licensed `pxz`.
- **If a function isn't in this file, it doesn't exist** in this SDK version. Don't generate code calling it.

## Modules

- [`pxz.core`](#pxzcore) — session, properties, undo/redo, logging, license
- [`pxz.io`](#pxzio) — file import / export, asset paths
- [`pxz.scene`](#pxzscene) — tree navigation, occurrences, components, materials, transforms
- [`pxz.algo`](#pxzalgo) — repair, tessellation, decimation, UV, baking, occlusion, mesh ops
- [`pxz.geom`](#pxzgeom) — geometry primitives and matrix math
- [`pxz.view`](#pxzview) — GPU viewer + offline rendering (screenshots)
- [`pxz.material`](#pxzmaterial) — materials, images/textures, shader patterns
- [`pxz.polygonal`](#pxzpolygonal) — mesh definitions, Draco, checksums
- [`pxz.cad`](#pxzcad) — exact BRep modeling (curves, surfaces, topology, booleans)
- [`pxz.raytrace`](#pxzraytrace) — offline ray-traced still rendering

---

## `pxz.core`

Session, properties, undo/redo, logging, license, callbacks.

### Notable classes / enums

```python
class Verbose(IntEnum)            # log levels for addConsoleVerbose / log
class PropertyType(IntEnum)
class Stability(IntEnum)
class InheritableBool(IntEnum)
class Color
class ColorAlpha
class Format
class LicenseInfos
class WebLicenseInfo
class FunctionDesc / GroupDesc / ModuleDesc / TypeDesc / EventDesc / ParameterDesc / FieldDesc / EnumPropertyInfo / ConstantDesc
class IdentPair / StringPair
```

### Entities (low-level CRUD; rarely needed in scripts)

```python
def cloneEntity(entity: int) -> int
def createEntity(type: int) -> int
def deleteEntities(entities: list[int]) -> None
def entityExists(entity: int) -> bool
def getAllEntities() -> list[int]
def getEntitiesByType(type: int, includeUnsubscribed: bool) -> list[int]
def getEntityType(entity: int) -> int
def getEntityTypeString(entity: int) -> str
def getTypeStats() -> list[list[int]]
def lockEntityRegistration() -> None
def unlockEntityRegistration() -> None
```

### Session / file

```python
def getCurrentPiXYZFile() -> str
def isCurrentPiXYZFileModified() -> bool
def load(fileName: str) -> None
def save(fileName: str) -> None
def resetSession() -> None
def unsavedUserChanges() -> bool
def stopProcess() -> None
```

### Properties (entity-level, custom)

```python
def addCustomProperty(entity: int, name: str, value: str = "", type: PropertyType = 0) -> None
def addCustomProperties(entities: list[int], names: list[str], values: list[str] = [], types: list[PropertyType] = []) -> None
def hasCustomProperty(entityId: int, customPropertyName: str) -> bool
def removeCustomProperty(entity: int, name: str) -> None
def supportCustomProperties(entity: int) -> bool
def hasProperty(entity: int, propertyName: str) -> bool
def getProperty(entity: int, propertyName: str) -> str
def getProperties(entities: list[int], propertyName: str, defaultValue: str = "") -> list[str]
def setProperty(entity: int, propertyName: str, propertyValue: str) -> str
def setProperties(entities: list[int], propertyNames: list[str], propertyValues: list[str]) -> None
def unsetProperty(entity: int, propertyName: str) -> None
def listProperties(entity: int) -> list[PropertyInfo]
def listPropertiesBatch(entities: list[int]) -> list[list[PropertyInfo]]
def getPropertyInfo(entity: int, propertyName: str) -> PropertyInfo
def listEnumLabels(enumType: int) -> EnumPropertyInfo
```

### Module properties

```python
def getModuleProperty(module: str, propertyName: str) -> str
def setModuleProperty(module: str, propertyName: str, propertyValue: str) -> str
def restoreModulePropertyDefaultValue(module: str, propertyName: str) -> str
def listModuleProperties(module: str) -> list[PropertyInfo]
def getModulePropertyInfo(module: str, propertyName: str) -> PropertyInfo
```

### Undo / redo

```python
def startUndoRedoStep(stepName: str, userData: str = "") -> None
def endUndoRedoStep(deleteIfEmpty: bool = True) -> None
def undo(count: int = 1) -> None
def redo(count: int = 1) -> None
def clearUndoRedo() -> None
def getUndoStack() -> list[str]
def getRedoStack() -> list[str]
def getUndoStepUserData(index: int) -> str
def getRedoStepUserData(index: int) -> str
def hasRecordingStep() -> bool
def toggleUndoRedo() -> None
```

### Logging

```python
def log(message: str, level: Verbose) -> None
def addConsoleVerbose(level: Verbose) -> None
def removeConsoleVerbose(level: Verbose) -> None
def hasConsoleVerbose(level: Verbose) -> bool
def addLogFileVerbose(level: Verbose) -> None
def removeLogFileVerbose(level: Verbose) -> None
def addSessionLogFileVerbose(level: Verbose) -> None
def removeSessionLogFileVerbose(level: Verbose) -> None
def configureInterfaceLogger(enableFunction: bool, enableParameters: bool, enableExecutionTime: bool) -> None
def configureFunctionLogger(functionName: str, enableFunction: bool, enableParameters: bool, enableExecutionTime: bool) -> None
def getInterfaceLoggerConfiguration() -> dict
def getLogFile() -> str
def setLogFile(path: str, keepHistory: bool = False) -> None
def setCoreDumpFile(path: str) -> None
```

### Version / runtime info

```python
def getVersion() -> str
def getCustomVersionTag() -> str
def getProductName() -> str
def getPixyzWebsiteURL() -> str
def getTempDirectory() -> str
def availableMemory() -> dict
def getMemoryUsagePeak() -> int
def checkForUpdates() -> dict
def clearOtherTemporaryDirectories() -> None
def setCurrentThreadAsProcessThread() -> None
```

### License (init-only, do not call from UPA)

```python
def checkLicense() -> bool
def configureLicenseServer(address: str, port: int, flexLM: bool = True) -> None
def installLicense(licensePath: str, user: bool = False) -> None
def generateActivationCode(filePath: str) -> None
def generateDeactivationCode(filePath: str) -> None
def getCurrentLicenseInfos() -> LicenseInfos
def getLicenseError() -> dict
def getLicenseServer() -> dict
def getRemainingSecondsBeforeLicenseTimeout() -> float
def addWantedToken(tokenName: str) -> None
def removeWantedToken(tokenName: str) -> None
def listWantedTokens() -> list[str]
def listOwnedTokens() -> list[str]
def listTokens(onlyMandatory: bool = False) -> list[str]
def needToken(tokenName: str) -> None
def releaseToken(tokenName: str) -> None
def ownToken(tokenName: str) -> bool
def tokenValid(tokenName: str) -> bool
def checkWebLogin(login: str, password: str) -> bool
def releaseWebLicense(login: str, password: str, id: int) -> None
def requestWebLicense(login: str, password: str, id: int) -> None
def retrieveWebLicenses(login: str, password: str) -> list[WebLicenseInfo]
def defineCaptchaCallback(callback: Callable[[str, list[Byte]], None]) -> None
```

### Parallelism

```python
def parallelStart(progression: bool = False, name: str = "Parallel session", jobCount: int = -1) -> Ptr
def parallelAddJob(session: Ptr, jobCallback: Callable[[Ptr], None], dataPtr: Ptr) -> None
def parallelFinish(session: Ptr) -> None
```

### Progression

```python
def pushProgression(stepCount: int, progressName: str = "") -> None
def popProgression() -> None
def stepProgression(stepCount: int = 1) -> None
```

### Module introspection (rare in scripts)

```python
def getModules() -> list[ModuleDesc]
def getModulesName() -> list[str]
def getModuleDescFromXML(xmlPath: str, addToModules: bool) -> ModuleDesc
def removeModule(module: str) -> None
def getModuleTypes(moduleName: str) -> list[TypeDesc]
def getType(moduleName: str, typeNameStr: str) -> TypeDesc
def getTypeAttributes(moduleName: str, typeNameStr: str) -> list[StringPair]
def getFunction(moduleName: str, functionName: str) -> FunctionDesc
def getFunctions(moduleName: str, groupName: str) -> list[FunctionDesc]
def getGroup(moduleName: str, groupName: str) -> GroupDesc
def getGroups(moduleName: str) -> list[GroupDesc]
def getEvent(moduleName: str, eventName: str) -> EventDesc
def getEvents(moduleName: str, groupName: str) -> list[EventDesc]
```

### Callbacks (event-driven scripts only)

`add*Callback` / `remove*Callback` pairs exist for: `AfterEntityPropertyChanged`, `AfterModulePropertyChanged`, `AfterUndoRedo`, `AtExit`, `BeforeEntityPropertyChanged`, `BeforeModulePropertyChanged`, `BeforeSessionReset`, `BeforeUndoRedo`, `CurrentFileChanged`, `EnteringUnsafeMode`, `EntityDestroyed`, `LeavingUnsafeMode`, `LicenseClientDisconnected`, `LicenseClientReconnected`, `OnConsoleMessage`, `OnSessionReset`, `ProgressChanged`, `ProgressStepFinished`, `ProgressStepStart`, `DebugEvent`, `AfterCustomPropertyAdded`, `UndoRedoStackChanged`. Pattern: `addXxxCallback(callback, userdata) -> int` / `removeXxxCallback(id: int)`.

---

## `pxz.io`

File import / export, asset paths, custom IO callbacks.

### Notable classes / enums

```python
class FileFormat
class FileFormatDescription(IntEnum)
class PriorityImportLevel(IntEnum)
class Protocol(IntEnum)
class DropBoxAccess / LocalDirectoryAccess / LocalFileAccess / OpenStackAccess / OwnCloudAccess / WebDAVAccess
```

### Import

```python
def importScene(fileName: str, root: int = 0) -> int
def importFiles(fileNames: list[str], root: int = 0) -> list[int]
def importPicture(filename: str, root: int = 0) -> int
def importRemote3mxFile(filePath: str, origin: str = "", root: int = 0) -> int
def listVariants(fileName: str) -> list[str]
def loadReferencedData(component: int, recursively: bool) -> None
def unloadReferencedData(component: int) -> None
def applyAutoTessellate(part: int) -> None
def splitPointCloud(files: list[str], outputDirectory: str, minVoxSize: float, useKDTree: bool, aabb: geom.AABB = geom.AABB(), density: float = -1) -> None
```

### Export

```python
def exportScene(fileName: str, root: int = 0) -> None
def exportSelection(fileName: str, keepIntermediaryNodes: bool = False) -> None
```

> Format is **inferred from file extension only** — there is no `format=` / `binaryGLTF=` / `embedTextures=` / `exportLODs=` keyword. To get a GLB, save as `.glb`. To inject FBX/GLTF tuning, use `core.setModuleProperty("io", "<key>", "<value>")` before calling `exportScene` (the per-format options are exposed as module-properties, not function args).

### Format introspection

```python
def getImportFormats(forRuntimeOS: bool = True) -> list[core.Format]
def getExportFormats(forRuntimeOS: bool = True) -> list[core.Format]
def getFormatsDescriptions(forRuntimeOS: bool = True) -> list[FileFormat]
def getExtensionPriority(extensionName: str) -> PriorityImportLevel
```

### Asset paths

```python
def getAssetPaths() -> list[str]
def setAssetPaths(assetPaths: list[str]) -> None
def addAssetPaths(path: list[str]) -> None
def clearAssetPaths() -> None
def findInDirectories(filePath: str) -> str
```

### Custom IO

```python
def registerIOCallbacks(name: str, importCallback: Callable[[str, int], None], exportCallback: Callable[[int, str], None], fileFormats: list[FileFormat]) -> None
```

---

## `pxz.scene`

Tree navigation, occurrences, components, metadata, materials-on-occurrences, transforms, variants, animation, merging, finding.

### Notable classes / enums

```python
class ComponentType(IntEnum)         # used by hasComponent / getComponent / addComponent
class LightType(IntEnum)
class MergeHiddenPartsMode(IntEnum)
class MergeStrategy(IntEnum)
class Primitive_Type(IntEnum)
class ShapeType(IntEnum)
class UVGenerationMode(IntEnum)      # also exists in algo
class VisibilityMode(IntEnum)
class PartialLoad_Status(IntEnum)
class SceneChangeType(IntEnum) / SelectionChangeType(IntEnum) / VariantChangeType(IntEnum) / ComponentChangeType(IntEnum) / AnimChannelType(IntEnum)
class Filter / PackedTree / PropertyValue / RayHit / ResizeByMaximumSizeOptions
class JointDefinition / AnimChannelInfo / AnimationInfo / AnimPropertyBinder
class AnnotationDefinition / ProductViewDefinition / ProberInfo
class VariantDefinition / VariantMaterials / MaterialCount
```

### Tree navigation

```python
def getRoot() -> int
def getChildren(occurrence: int) -> list[int]
def getChildrenCount(occurrence: int) -> int
def getFirstChild(occurrence: int) -> int
def getNextSibling(occurrence: int) -> int
def getPreviousSibling(occurrence: int) -> int
def getParent(occurrence: int) -> int
def getAncestors(occurrence: int) -> list[int]
def getOccurrenceAncestors(occurrence: int) -> list[int]
def getOccurrencesAncestors(occurrences: list[int]) -> list[list[int]]
def isAncestorOf(maybeAncestor: int, occurrence: int) -> bool
def keepAncestors(occurrences: list[int]) -> list[int]
def getCurrentVariantRoot() -> int
def getSubTree(root: int = 0, visibilityMode: VisibilityMode = 1, depth: int = -1) -> PackedTree
def createSubTree(tree: PackedTree, root: int = 0, replaceRoot: bool = True) -> list[int]
def computeSubTreeChecksum(root: int = int()) -> str
def getSubTreeStats(roots: list[int]) -> dict
```

### Tree mutation

```python
def createOccurrence(name: str, parent: int = int()) -> int
def createOccurrences(name: str, parents: list[int] = []) -> list[int]
def createOccurrenceFromSelection(name: str, children: list[int], parent: int, keepMaterialAssignment: bool = True) -> int
def createOccurrenceFromText(text: str, font: str = "ChicFont", fontSize: int = 64, color: core.ColorAlpha = core.ColorAlpha(), heigth3D: float = 40) -> int
def deleteOccurrences(occurrences: list[int]) -> None
def deleteEmptyOccurrences(root: int = 0) -> None
def moveOccurrences(occurrences: list[int], destination: int, insertBefore: int = 0) -> None
def setParent(occurrence: int, parent: int, addInParentInstances: bool = False, insertBefore: int = int(), worldPositionStays: bool = False) -> None
def setOccurrenceName(occurrence: int, name: str) -> None
def renameLongOccurrenceName(maxLength: int) -> None
```

### Naming, geometry counts, bounds, volume

```python
def getOccurrenceName(occurrence: int) -> str
def getPolygonCount(occurrences: list[int], asTriangleCount: bool = False, countOnceEachInstance: bool = False, countHidden: bool = False) -> int
def getVertexCount(occurrences: list[int], countOnceEachInstance: bool = False, countHidden: bool = False, countPoints: bool = False, countMergedVertices: bool = False) -> int
def getAABB(occurrences: list[int], precise: bool = False) -> geom.AABB
def getMBB(occurrences: list[int], forcedAxis: geom.Point3 = geom.Vector3(0,0,0)) -> geom.OBB
def getOBB(occurrences: list[int]) -> geom.OBB
def getVolume(occurrence: int) -> float
def getVolumes(iRoots: list[int]) -> list[float]
```

### Visibility

```python
def hide(occurrences: list[int]) -> None
def show(occurrences: list[int]) -> None
def showOnly(occurrences: list[int]) -> None
def inverseVisibility(occurrences: list[int]) -> None
def getGlobalVisibility(occurrence: int) -> bool
def getHiddenPartOccurrences(roots: list[int] = []) -> list[int]
def getVisiblePartOccurrences(roots: list[int] = []) -> list[int]
def convertToOldSchoolVisibility(root: int = 0) -> None
```

### Transforms

```python
def getLocalMatrix(occurrence: int) -> list[list[float]]
def getLocalMatrices(occurrences: list[int]) -> list[list[list[float]]]
def getGlobalMatrix(occurrence: int) -> list[list[float]]
def getGlobalMatrices(occurrences: list[int]) -> list[list[list[float]]]
def setLocalMatrix(occurrence: int, matrix: list[list[float]]) -> None
def setLocalMatrices(occurrencesIds: list[int], matrices: list[list[list[float]]], batchSize: int) -> None
def applyTransformation(occurrence: int, matrix: list[list[float]]) -> None
def rotate(occurrence: int, axis: geom.Point3, angle: float) -> None
def createSymmetry(occurrences: list[int], plane: geom.AxisPlane) -> None
def resetTransform(root: int, recursive: bool = True, keepInstantiation: bool = True, keepPartTransform: bool = False) -> None
def resetPartTransform(root: int = 0) -> None
def removeSymmetryMatrices(occurrence: int = 0) -> None
```

### Pivot points

```python
def alignPivotPointToWorld(occurrences: list[int], applyToChildren: bool) -> None
def movePivotPointToOccurrenceCenter(occurrences: list[int], applyToChildren: bool) -> None
def movePivotPointToOrigin(occurrence: int, applyToChildren: bool) -> None
def movePivotPointToSelectionCenter(occurrences: list[int]) -> None
def movePivotPointToTargetedOccurrenceCenter(occurrences: list[int], target: int, applyToChildren: bool) -> None
def setPivotOnly(occurrence: int, pivot: list[list[float]]) -> None
```

### Components

```python
def addComponent(occurrence: int, componentType: ComponentType) -> int
def addComponents(occurrences: list[int], componentType: ComponentType) -> list[int]
def hasComponent(occurrence: int, componentType: ComponentType, followPrototypes: bool = True) -> bool
def getComponent(occurrence: int, componentType: ComponentType, followPrototypes: bool = True) -> int
def getComponents(occurrences: list[int], componentType: ComponentType, followPrototypes: bool = True) -> list[int]
def getComponentByOccurrence(occurrences: list[int], componentType: ComponentType, followPrototypes: bool = True) -> list[int]
def getComponentOccurrence(component: int) -> int
def getComponentType(component: int) -> ComponentType
def listComponent(componentType: ComponentType) -> list[int]
def listComponents(occurrence: int, followPrototypes: bool = True) -> list[int]
def setComponentOccurrence(component: int, occurrence: int) -> None
def deleteComponentByType(componentType: ComponentType, occurrence: int, followPrototypes: bool = True) -> None
def deleteComponentsByType(componentType: ComponentType, rootOccurrence: int = int()) -> None
def getOccurrencesWithComponent(componentType: ComponentType, fromOcc: int = int()) -> list[int]
```

### Metadata

```python
def addMetadata(metadata: int, name: str, value: str) -> None
def addMetadataBlock(metadata: int, names: list[str], values: list[str]) -> None
def getMetadata(metadata: int, name: str) -> str
def getMetadatasDefinitions(metadatas: list[int]) -> list[list[PropertyValue]]
def removeMetadata(metadata: int, name: str) -> None
def createMetadatasFromDefinitions(occurrences: list[int], definitions: list[list[PropertyValue]]) -> list[int]
```

### Materials on occurrences

```python
def getActiveMaterial(occurrence: int) -> int
def getActiveMaterials(occurrences: list[int]) -> list[int]
def getOccurrenceActiveMaterial(occurrence: int) -> int
def setOccurrenceMaterial(occurrence: int, material: int) -> None
def getMaterialsFromSubtree(occurrence: int) -> list[int]
def removeMaterials(roots: list[int] = []) -> None
def replaceMaterial(originalMaterial: int, newMaterial: int, occurrences: list[int] = []) -> None
def cleanUnusedMaterials(cleanImages: bool = False) -> int
def cleanUnusedImages() -> int
def mergeMaterials(materials: list[int] = [], evaluateNames: bool = False) -> int
def mergeImages(images: list[int] = []) -> int
def convertMaterialsToColor(materials: list[int] = []) -> None
def convertMaterialsToPBR(materials: list[int] = []) -> None
def transferCADMaterialsOnPartOccurrences(rootOccurrence: int = int()) -> None
def transferMaterialsOnPatches(rootOccurrence: int = int()) -> None
def resizeTextures(inputMode: list, resizeMode: list, replaceTextures: bool) -> None
```

### Sub-part / variant materials

```python
def getMaterialsFromSubPart(component: int) -> list[int]
def getSubpartMaterial(occurrence: int, subpartIndex: int) -> int
def listActiveShapeMaterials(part: int) -> list[int]
def listSubpartMaterials(occurrence: int) -> list[int]
def listSubpartVariantMaterials(occurrence: int) -> list[VariantMaterials]
def setSubpartMaterial(occurrence: int, subpartIndex: int, material: int) -> None
def setSubpartMaterials(occurrence: int, materials: list[int], startIndex: int = 0) -> None
def setSubpartVariantMaterials(occurrence: int, variantMaterials: list[VariantMaterials]) -> None
def setSubpartVariantMaterialsList(variants: list[int], materialListList: list[list[int]]) -> list[VariantMaterials]
def transferSubpartMaterialsOnPatches(occurrence: int) -> None
```

### Parts / shapes / meshes

```python
def getPartOccurrences(fromOcc: int = int()) -> list[int]
def getBrepShape(part: int) -> int
def getPartActiveShape(part: int) -> int
def getPartLocalMatrix(part: int) -> list[list[float]]
def getPartShapeType(part: int) -> ShapeType
def getPartMesh(part: int) -> int
def getPartModel(part: int) -> int
def getPartsMeshes(parts: list[int]) -> list[int]
def getPartsModels(parts: list[int]) -> list[int]
def getPartsTransforms(parts: list[int]) -> list[list[list[float]]]
def getPartsTransformsIndexed(parts: list[int]) -> dict
def setPartMesh(part: int, mesh: int) -> None
def setPartModel(part: int, model: int) -> None
def setPartsTransforms(parts: list[int], transforms: list[list[list[float]]]) -> None
def setPartsTransformsIndexed(parts: list[int], indices: list[int], transforms: list[list[list[float]]]) -> None
def createPartsFromMeshes(occurrences: list[int], meshes: list[int]) -> list[int]
def createSceneFromMeshes(meshes: list[int], matrices: list[list[list[float]]], centerPartPivots: bool = True) -> int
def createOBBMesh(occurrence: int) -> int
```

### Active properties (read evaluated values)

```python
def getActivePropertyValue(occurrence: int, propertyName: str, cacheProperty: bool = False) -> str
def getActivePropertyValues(occurrences: list[int], propertyName: str, cacheProperty: bool = False) -> list[str]
```

### Find

```python
def findOccurrencesByMaterial(material: int) -> list[int]
def findOccurrencesByMetadata(property: str, regex: str, roots: list[int] = [], caseInsensitive: bool = False) -> list[int]
def findOccurrencesByMetadataValue(regex: str, roots: list[int] = [], caseInsensitive: bool = False) -> list[int]
def findOccurrencesByProperty(property: str, regex: str, roots: list[int] = [], caseInsensitive: bool = False) -> list[int]
def findPartOccurrencesByActiveMaterial(material: int, roots: list[int] = []) -> list[int]
def findPartOccurrencesByMaximumSize(roots: list[int], maxDiagLength: float, maxSize: float = -1, getHidden: bool = False) -> list[int]
def findPartOccurrencesByMinimumNumberOfInstances(minInstanciationCount: int) -> list[int]
def findPartOccurrencesByVisibleMaterial(material: int) -> list[int]
def findPartOccurrencesInAABB(aabb: geom.AABB) -> list[int]
def findPartOccurrencesInBox(box: geom.ExtendedBox, strictlyIncludes: bool) -> list[int]
def findDuplicatedPartOccurrences(root: int = 0, acceptVolumeRatio: float = 0.01, acceptPolycountRatio: float = 0.1, acceptAABBAxisRatio: float = 0.01, acceptAABBCenterDistance: float = 0.1) -> list[int]
def getPartOccurrencesGroupedBySimilarity(root: int = 0, acceptVolumeRatio: float = 0.01, acceptPolycountRatio: float = 0.1, acceptAABBAxisRatio: float = 0.01, acceptAABBCenterDistance: float = 0.1) -> list[list[int]]
```

### Filter expressions

```python
def addFilterToLibrary(name: str, expr: str) -> int
def removeFilterFromLibrary(filterId: int) -> None
def listFilterLibrary() -> list[Filter]
def findFilterByName(name: str) -> Filter
def getFilterFromLibrary(filterId: int) -> Filter
def getFilterExpression(filterId: int) -> str
def importFilterLibrary(file: str) -> None
def exportFilterLibrary(file: str) -> None
def evaluateExpression(filter: str) -> str
def evaluateExpressionOnOccurrences(occurrences: list[int], filter: str) -> list[str]
def evaluateExpressionOnSubTree(filter: str, fromOcc: int = int()) -> dict
def getFilteredOccurrences(filter: str, fromOcc: int = int()) -> list[int]
```

### Selection (server-side selection state — not needed in headless scripts)

```python
def select(occurrences: list[int], selectionId: int = 1) -> None
def unselect(occurrence: list[int], selectionId: int = 1) -> None
def invertSelect(occurrence: list[int], selectionId: int = 1) -> None
def invertSelection(selectionId: int = 1) -> None
def invertOrientationSelection(selectionId: int = 1) -> None
def clearSelection(selectionId: int = 1) -> None
def deleteSelection(selectionId: int = 1) -> None
def createSelectionSnapshot() -> int
def deleteSelectionSnapshot(selectionId: int) -> None
def getSelectedOccurrences(keepAncestors: bool = False, selectionId: int = 1) -> list[int]
def getSelectedPolygonCount(selectionId: int = 1) -> int
def separateSelection(createSingleOccurrence: bool = True, selectionId: int = 1) -> list[int]
```

> In a UPA script just pass `list[int]` directly to `algo.*` functions — no need to `select()` first.

### Isolate

```python
def isolate(occurrences: list[int]) -> None
def unisolate() -> None
def isIsolated() -> bool
def getIsolatedOccurrences() -> list[int]
```

### Merging

```python
def mergePartOccurrences(partOccurrences: list[int], mergeHiddenPartsMode: MergeHiddenPartsMode = 2) -> list[int]
def mergePartOccurrencesByAssemblies(roots: list[int] = [], mergeHiddenPartsMode: MergeHiddenPartsMode = 2) -> None
def mergePartOccurrencesByFinalAssemblies(roots: list[int] = [], mergeHiddenPartsMode: MergeHiddenPartsMode = 0, CollapseToParent: bool = True) -> None
def mergePartOccurrencesByMaterials(partOccurrences: list[int], mergeNoMaterials: bool = True, mergeHiddenPartsMode: MergeHiddenPartsMode = 2, combineMeshes: bool = True) -> list[int]
def mergePartOccurrencesByName(root: int = 0, mergeHiddenPartsMode: MergeHiddenPartsMode = 2) -> None
def mergePartOccurrencesByRegions(roots: list[int], mergeBy: list, strategy: MergeStrategy) -> list[int]
def mergePartOccurrencesWithSingleOpenShellByAssemblies(root: int) -> list[int]
def mergeOccurrencesByTreeLevel(roots: list[int], maxLevel: int, mergeHiddenPartsMode: MergeHiddenPartsMode = 2) -> None
def findPartOccurrencesWithUnstitchedOpenShells(root: int) -> list[int]
```

### Instances / prototypes

```python
def getPrototype(occurrence: int) -> int
def getPrototypes(occurrences: list[int]) -> list[int]
def getFinalPrototype(occurrence: int) -> int
def getInstances(occurrence: int) -> list[int]
def getDirectInstances(prototype: int) -> list[int]
def setPrototype(occurrence: int, prototype: int) -> None
def setPrototypes(occurrences: list[int], prototypes: list[int]) -> None
def updateChildrenPrototypes(occurrence: int) -> None
def addInParentInstances(root: int) -> None
def cleanInstances(removeUselessInstances: bool, removeHierarchyOverridingInstances: bool, occurrence: int = 0) -> None
def makeInstanceUnique(occurrences: list[int] = 0, keepOnlyPartInstances: bool = False) -> None
def prototypeSubTree(prototype: int) -> int
def rake(occurrence: int = 0, keepInstances: bool = False) -> None
def compress(occurrence: int = 0) -> int
```

### Primitives (shape generators)

```python
def createCapsule(radius: float, height: float, subdivisionLatitude: int = 16, subdivisionLongitude: int = 16, generateUV: bool = True) -> int
def createCone(bottomRadius: float, height: float, sides: int = 16, generateUV: bool = True) -> int
def createCube(sizeX: float, sizeY: float, sizeZ: float, subdivision: int = 1, generateUV: bool = True) -> int
def createCylinder(radius: float, height: float, sides: int = 16, generateUV: bool = True) -> int
def createImmersion(radius: float, subdivisionX: int, subdivisionY: int) -> int
def createPlane(sizeX: float, sizeY: float, subdivisionX: int = 1, subdivisionY: int = 1, generateUV: bool = True) -> int
def createSphere(radius: float, subdivisionLatitude: int = 16, subdivisionLongitude: int = 16, generateUV: bool = True) -> int
def createTorus(majorRadius: float, minorRadius: float, subdivisionLatitude: int = 16, subdivisionLongitude: int = 16, generateUV: bool = True) -> int
```

### Lights

```python
def addLightComponent(occurrence: int, lightType: LightType, color: core.Color, power: float = 1.0, cutOff: float = 20.0) -> int
def createLight(name: str, lightType: LightType, color: core.Color, power: float = 1.0, cutOff: float = 20.0, parent: int = 0) -> int
```

### Variants

```python
def addVariant(name: str) -> int
def duplicateVariant(variant: int, name: str) -> int
def removeVariant(variant: int) -> None
def listVariants() -> list[int]
def setCurrentVariant(variant: int = int()) -> None
def setDefaultVariant() -> None
def getVariantTree(variant: int) -> int
def setVariantTree(variant: int, tree: int) -> None
def startModifyAllVariants() -> None
def endModifyAllVariants() -> None
def getVariantComponentsDefinitions(variantComponents: list[int]) -> list[list[VariantDefinition]]
```

### Alternative trees

```python
def createAlternativeTree(name: str, root: int = int()) -> int
def listAlternativeTrees() -> list[int]
def getAlternativeTreeRoot(tree: int) -> int
```

### Annotations / PMI

```python
def addAnnotationGroup(component: int, name: str) -> int
def addAnnotationToProductView(productView: int, annotation: int) -> None
def addMeshToAnnotation(annotation: int, material: int, staticmesh: int) -> None
def convertPMIToOccurrences(occurrences: list[int], convertVisibility: bool = False) -> None
def createAnnotationFromDefinition(definition: AnnotationDefinition) -> int
def createOccurrenceFromAnnotation(annotation: int, convertVisibility: bool = False) -> int
def createProductView(definition: ProductViewDefinition) -> int
def getAnnotationDefinition(annotation: int) -> AnnotationDefinition
def getAnnotationGroups(pmiComponent: int) -> list[int]
def getAnnotationListAABB(annotationList: list[int]) -> geom.AABB
def getAnnotations(group: int) -> list[int]
def getOccurrenceAnnotationDefinitions(occurrence: int) -> list[AnnotationDefinition]
def getProductViewDefinition(view: int) -> ProductViewDefinition
def getProductViewDefinitions() -> list[ProductViewDefinition]
def setAnnotationToGroup(annotation: int, group: int) -> None
```

### Animation

```python
def createAnimation(name: str) -> int
def addAnimation(animation: int) -> None
def deleteAnimation(animation: int) -> None
def deleteEmptyAnimation() -> None
def listAnimations() -> list[int]
def getAnimationInfo(animation: int) -> AnimationInfo
def addKeyframe(channel: int, time: int, value: float) -> int
def addKeyframeFromCurrentPosition(channel: int, time: int) -> None
def removeKeyframe(channel: int, time: int) -> None
def getKeyframes(channel: int) -> list[int]
def getKeyframeParentAnimChannel(keyframe: int) -> int
def displayAllKeyframesFromAnimChannel(channel: int) -> None
def displayAllKeyframesFromAnimation(animation: int) -> None
def displayValueFromAnimChannelAtTime(channel: int, time: int, defaultValue: bool = False) -> None
def makeDefaultKeyframe(channel: int) -> None
def decimateAnimChannelBySegment(channel: int, precision: float) -> None
def bakeAnimation(animation: int, occurrence: int, end: int, interval: int) -> None
def moveAnimation(animation: int, target: int, newParent: int, interval: int) -> None
def animatesThisOccurrence(animation: int, occurrence: int) -> bool
def getAnimChannelIfExists(animation: int, occurrence: int) -> int
def getAnimChannelInfo(channel: int) -> AnimChannelInfo
def getAnimChannelOccurrence(channel: int) -> int
def getMainChannel(channel: int) -> int
def getParentChannel(channel: int) -> int
def getSubChannel(channel: int, name: str) -> int
def getSubChannels(channel: int) -> list[int]
def listMainChannels(animation: int) -> list[int]
def linkPropertyToAnimation(animation: int, entity: int, propertyName: str) -> int
def unlinkPropertyToAnimation(animation: int, entity: int, propertyName: str) -> None
def getAnimationComponentPropertyBinderLists(animationComponent: int) -> list[AnimPropertyBinder]
def getAnimationPropertyBinderLists(animation: int) -> list[AnimPropertyBinder]
def createSkeletonMesh(root: int) -> int
def getJointDefinition(joint: int) -> JointDefinition
def getJointDefinitions(joints: list[int]) -> list[JointDefinition]
def getOccurrenceJoint(occurrence: int) -> int
```

### BRep / tessellation introspection

```python
def getBRepInfos() -> dict
def getTessellationInfos(root: int = 0) -> dict
def getTessellationParameters(part: int) -> dict
def print(root: int = 0) -> None
```

### Cluster / octree

```python
def createHierarchicalClusters(root: int, childrenCountByNode: int = 2, minFitting: float = -1) -> int
def generateOctaViews(radius: float, XFrames: int, YFrames: int, hemi: bool = False) -> int
def generateOctree(occurrence: int, maxDepth: int = 5, looseFactor: float = 2) -> int
def getClusters(occurrences: list[int], strategy: list) -> list[list[int]]
```

### Ray probing

```python
def createRayProber() -> int
def createSphereProber() -> int
def rayCast(ray: geom.Ray, root: int) -> RayHit
def rayCastAll(ray: geom.Ray, root: int) -> list[RayHit]
def updateRayProber(proberID: int, ray: geom.Ray) -> None
def updateSphereProber(proberID: int, sphereCenter: geom.Point3, sphereRadius: float) -> None
```

### Referenced data (lazy loading)

```python
def getPartialLoadingStatus(component: int) -> PartialLoad_Status
def setReferencedDataComponentParent(component: int, parent: int) -> None
def setReferencedDataComponentPath(component: int, filePath: str) -> None
```

### Cavity / viewpoint heuristics

```python
def getViewpointsFromCavities(voxelSize: float, minCavityVolume: float) -> dict
```

### User data per occurrence/part

`getOccurrenceUserData` / `setOccurrenceUserData` / `hasOccurrenceUserData` / `unsetOccurrenceUserData` / `subscribeToOccurrenceUserData` / `unsubscribeFromOccurrenceUserData` and the multi-occurrence (`getMultipleOccurrenceUserData`, etc.) and per-part (`getPartUserData`, …) variants.

### Locking (advanced)

```python
def sceneReadLock() -> None
def sceneReadUnlock() -> None
def sceneTryReadLock() -> bool
def sceneWriteLock() -> None
def sceneWriteUnlock() -> None
```

### Callbacks

`addComponentChangedCallback`, `addSceneChangedCallback`, `addAnimationAdded/Changed/Cleared/RemovedCallback`, `addIsolateBegan/EndedCallback`, `addSelectionChangedCallback`, `addVariantChangedCallback`, `addonRayProbeCallback`, `addonSphereProbeCallback` — each with a matching `removeXxx(id: int)`.

---

## `pxz.algo`

The big one — repair, tessellation, decimation, UV, baking, occlusion, mesh ops.

### Notable enums (used as parameters)

```python
class AlignmentMode(IntEnum)
class AttributeType(IntEnum)
class ComputingQuality(IntEnum)
class ConvexityFilter(IntEnum)
class CostEvaluation(IntEnum)
class CreateOccluder(IntEnum)
class DiskSegmentationMethod(IntEnum)
class ElementFilter(IntEnum)
class FeatureType(IntEnum)
class FilletingMode(IntEnum)
class FlatteningStopCondition(IntEnum)
class InnerOuterOption(IntEnum)
class MeshBooleanOperation(IntEnum)
class OrientStrategy(IntEnum) / OrientStrategyAdvanced(IntEnum)
class QualityMemoryTradeoff(IntEnum) / QualitySpeedTradeoff(IntEnum)
class RatioUV3DMode(IntEnum)
class RelaxUVMethod(IntEnum)
class ReplaceByBoxType(IntEnum) / ReplaceByMode(IntEnum)
class SawingMode(IntEnum)
class SelectionLevel(IntEnum)         # Polygons / Patches / Parts
class Space(IntEnum)
class TransformationType(IntEnum)
class UVGenerationMode(IntEnum)        # NoUV, etc.
class UVImportanceEnum(IntEnum)
class UnwrapUVMethod(IntEnum)
class VertexWeightStrategy(IntEnum)
class VisibilityToWeightMode(IntEnum)
```

### Notable parameter classes

```python
class BakeMaps:
    diffuse: bool
    normal: bool
    roughness: bool
    metallic: bool
    opacity: bool
    ambientOcclusion: bool
    emissive: bool
    def __init__(self, diffuse, normal, roughness, metallic, opacity, ambientOcclusion, emissive) -> None

class BakeOption:
    resolution: int          # texture resolution in pixels (square)
    padding: int             # padding around UV islands in pixels
    textures: BakeMaps       # which maps to bake
    def __init__(self, resolution, padding, textures) -> None

class BakedValue:
    occurrence: int
    polygonId: int
    paramU: float
    paramV: float
    material: int

class Box / BoxParameters / Cylinder / CylinderParameters / Sphere / SphereParameters
class CapsuleParameters / ConeParameters / HexahedronParameters / PlaneParameters
class Plane
class Feature / FeatureInput / OccurrenceFeatures
class OctahedralImpostor
class ReplaceByOccurrenceOptions / ReplaceByPrimitiveOptions
class BricksReturn
```

### CAD assembly / repair

```python
def assembleCAD(occurrences: list[int], tolerance: float, removeDuplicatedFaces: bool = True) -> None
def repairCAD(occurrences: list[int], tolerance: float, orient: bool = True) -> None
def backToInitialBRep(occurrences: list[int]) -> None
def crackCADMoebiusStrip(occurrences: list[int]) -> None
def crackEdges(occurrences: list[int], useAttributesFilter: bool = True, sharpAngleFilter: float = 45, useNonManifoldFilter: bool = False) -> None
def crackMeshEdges(occurrences: list[int], normal: bool = False, uvs: bool = False, uvChannels: list[int] = [], loi: bool = False, patches: bool = False, nman: bool = False) -> None
def crackMoebiusStrips(occurrences: list[int], maxEdgeCount: int = 3) -> None
def crackNonManifoldVertices(occurrences: list[int]) -> None
def deleteBRepShapes(occurrences: list[int], onlyTessellated: bool = True) -> None
def getAllAxisFromCADModel(occurrences: list[int]) -> dict
def listFeatures(occurrences: list[int], throughHoles: bool = True, blindHoles: bool = False, maxDiameter: float = -1) -> list[OccurrenceFeatures]
def setFeatureComponentMaxIndex(occurrences: list[int], maxIndex: int) -> None
```

### Tessellation

```python
def tessellate(occurrences: list[int], maxSag: float, maxLength: float, maxAngle: float, createNormals: bool = True, uvMode: UVGenerationMode = 0, uvChannel: int = 1, uvPadding: float = 0.0, createTangents: bool = False, createFreeEdges: bool = False, keepBRepShape: bool = True, overrideExistingTessellation: bool = False) -> None
def tessellateRelativelyToAABB(occurrences: list[int], maxSag: float, sagRatio: float, maxLength: float, maxAngle: float, createNormals: bool = True, uvMode: UVGenerationMode = 0, uvChannel: int = 1, uvPadding: float = 0.0, createTangents: bool = False, createFreeEdges: bool = False, keepBRepShape: bool = True, overrideExistingTessellation: bool = False) -> None
def tessellatePointClouds(occurrences: list[int], kNeighbors: int = 20, keepPoints: bool = False, colorize: bool = True) -> None
def getTessellations(occurrences: list[int]) -> list[int]
```

### Decimation / simplification

```python
def decimate(occurrences: list[int], surfacicTolerance: float, lineicTolerance: float = 0.1, normalTolerance: float = 5, texCoordTolerance: float = -1, releaseConstraintOnSmallArea: bool = False) -> None
def decimateEdgeCollapse(occurrences: list[int], surfacicTolerance: float, boundaryWeight: float = 1., normalWeight: float = 1., UVWeight: float = 1., sharpNormalWeight: float = 1., UVSeamWeight: float = 10., normalMaxDeviation: float = -1, forbidUVOverlaps: bool = True, UVMaxDeviation: float = -1, UVSeamMaxDeviation: float = -1, protectTopology: bool = False, qualityTradeoff: QualitySpeedTradeoff = 0) -> None
def decimateTarget(occurrences: list[int], targetStrategy: list, UVImportance: UVImportanceEnum = 0, protectTopology: bool = False, iterativeThreshold: int = 5000000, processMeshIndependently: bool = False, maxQuadricAge: int = -1) -> None
def decimatePointClouds(occurrences: list[int], tolerance: float = 500) -> None
def evalDecimateErrorForTarget(occurrences: list[int], TargetStrategy: list, boundaryWeight: float = 1., normalWeight: float = 1., UVWeight: float = 1., sharpNormalWeight: float = 1., UVSeamWeight: float = 10., forbidUVFoldovers: bool = True, protectTopology: bool = False) -> float
```

`targetStrategy` and `TargetStrategy` are list-typed; common shapes include `["ratio", float]` and `["polygonCount", int]` based on observed usage in this repo.

### Mesh repair / cleanup

```python
def repairMesh(occurrences: list[int], tolerance: float, crackNonManifold: bool = True, orient: bool = True) -> None
def repairNullNormals(occurrences: list[int]) -> None
def removeDegeneratedPolygons(occurrences: list[int], tolerance: float) -> None
def removeMultiplePolygon(occurrences: list[int]) -> None
def removeZFighting(occurrences: list[int]) -> float
def sewBoundary(occurrences: list[int], maxDistance: float) -> None
def separateToManifold(occurrences: list[int]) -> None
def remeshSurfacicHoles(occurrences: list[int], maxDiameter: float = 0, refine: bool = True, numberOfNeighbors: int = 3, fillWithMaterial: int = 0) -> None
def vertexOffset(occurrences: list[int], offset: float = 1) -> None
def deleteFreeVertices(occurrences: list[int]) -> None
def deleteLines(occurrences: list[int]) -> None
def deleteNormals(occurrences: list[int]) -> None
def deletePatches(occurrences: list[int], keepOnePatchByMaterial: bool = True) -> None
def deletePolygons(occurrences: list[int]) -> None
def deleteTangents(occurrences: list[int]) -> None
def deleteTextureCoordinates(occurrences: list[int], channel: int = -1) -> None
def deleteVisibilityPatches(occurrences: list[int]) -> None
def removeHoles(occurrences: list[int], throughHoles: bool, blindHoles: bool, surfacicHoles: bool, maxDiameter: float, fillWithMaterial: int = 0) -> None
def filterHiddenPolygons(occurrences: list[int], voxelSize: float) -> None
def filterMeshVertexColors(occurrences: list[int], sigmaPos: float = 5.0, sigmaValue: float = 0.2, sigmaNormal: float = 15.0) -> None
def smoothMesh(occurrences: list[int], mode: CostEvaluation, maxIterations: int = 100, lockSignificantEdges: bool = True) -> None
def barySmooth(occurrences: list[int], iteration: int = 1) -> None
def loopSubdivMesh(occurrences: list[int], depth: int) -> None
def mergeVertices(occurrences: list[int], maxDistance: float, mask: polygonal.TopologyCategoryMask) -> None
def moebiusCracker(occurrences: list[int]) -> None
def noiseMesh(occurrences: list[int], maxAmplitude: float) -> None
def equilateralize(occurrences: list[int], maxIterations: int = 1) -> None
def quadify(occurrences: list[int]) -> None
def requadify(occurrences: list[int], forceFullQuad: bool = True) -> None
def triangularize(occurrences: list[int]) -> None
def filletMesh(occurrences: list[int], value: float, filletingMode: FilletingMode = 0, subdivisionNb: int = 0, createFlatChamfer: bool = False, material: int = int(), uvChannel: int = -1) -> None
def sweep(occurrences: list[int], radius: float, sides: int, createNormals: bool, keepLines: bool, generateUV: bool) -> None
def transferUV(source: int, destination: int, sourceChannel: int = 0, destinationChannel: int = 0, tolerance: float = 0.001) -> None
def extractNeutralAxis(occurrences: list[int], maxDiameter: float, removeOriginalMesh: bool) -> None
def segmentMesh(occurrences: list[int], overwriteLoI: bool = True) -> None
```

### Normals / tangents / patches / lines

```python
def createNormals(occurrences: list[int], sharpEdge: float = 45, override: bool = True, useAreaWeighting: bool = False) -> None
def createTangents(occurrences: list[int], uvChannel: int = 0, override: bool = True) -> None
def invertTangents(occurrences: list[int], invertW: bool = True) -> None
def invertPolygonFacesOrientation(occurrences: list[int]) -> None
def orientNormals(occurrences: list[int]) -> None
def orientFromFace() -> None
def orientPolygonFaces(occurrences: list[int], makeOrientable: bool = True, useArea: bool = False, orientStrategy: OrientStrategy = 0) -> None
def orientPolygonFacesAdvanced(occurrences: list[int], voxelSize: float, minimumCavityVolume: float, resolution: int, mode: InnerOuterOption = 0, considerTransparentOpaque: bool = True, orientStrategy: OrientStrategyAdvanced = 0) -> None
def orientPolygonFacesFromCamera(occurrences: list[int], cameraPosition: geom.Point3, cameraDirection: geom.Point3, cameraUp: geom.Point3, resolution: int, fovX: float = 90) -> None
def identifyLinesOfInterest(occurrences: list[int], normal: bool = False, uvs: bool = False, uvChannels: list[int] = [], border: bool = False, patches: bool = False, nman: bool = False) -> None
def identifyPatches(occurrences: list[int], useAttributesFilter: bool = True, sharpAngleFilter: float = 45, useBoundaryFilter: bool = True, useNonManifoldFilter: bool = True, useLineEdgeFilter: bool = True, useQuadLineFilter: bool = False) -> None
def identifySharpEdges(occurrences: list[int], minSharpAngle: float, maxSharpAngle: float = 180, convexity: ConvexityFilter = 2, onlyExplicitSharp: bool = False) -> None
def createFreeEdgesFromPatches(occurrences: list[int]) -> None
def createIdentifiedPatchesFromPatches(occurrences: list[int]) -> None
def createIndexMapFromOccurrences(occurrences: list[int], uvChannel: int, createTexture1D: bool) -> int
def createVisibilityPatchesFromPatch(occurrences: list[int]) -> None
def lineToTexture(lines: list[int], useColor: list, resolution: int = 512, thickness: int = 5) -> None
def deleteAttribute(occurrence: int, type: AttributeType) -> None
def calculateNormalsInPointClouds(occurrences: list[int]) -> None
def createPointCloudKDTree(occurrences: list[int], depth: int, addToScene: bool = True) -> int
def voxelizePointClouds(occurrences: list[int], voxelSize: float = 500) -> None
```

### Mesh comparison / diagnostics

```python
def meshComparison(mesh_1: int, mesh_2: int) -> float
def meshComparisonBatch(meshes1: list[int], meshes2: list[int]) -> list[float]
def meshIntersections(occurrencesA: list[int], occurrencesB: list[int]) -> list[list[geom.Point3]]
def meshBooleanOperation(occurrencesA: list[int], occurrencesB: list[int], operation: MeshBooleanOperation) -> int
def getVisualComparisonFootprint(originalOccurrences: list[int], comparedOccurrences: list[int], resolution: int = 512, viewpointCount: int = 256, threshold: float = 0.2, onHemisphereOnly: bool = False) -> float
def getMeshVertexColors(occurrences: list[int]) -> list[list[core.ColorAlpha]]
def setMeshVertexColors(occurrences: list[int], vertexColors: list[list[core.ColorAlpha]]) -> None
def createVertexColorFromMaterials(occurrenceList: list[int]) -> None
def findBestPivotBetweenOccurrences(assembly1: list[int], assembly2: list[int], precision: float = -1) -> list[list[float]]
def getOptimalTextureResolution(occurrences: list[int], texelPerMm: float) -> int
def optimizeTextureSize(root: int, texelPerMm: float) -> None
```

### Optimisation (general)

```python
def optimizeCADLoops(occurrences: list[int]) -> None
def optimizeForRendering(occurrences: list[int]) -> None
def optimizeSubMeshes(occurrences: list[int]) -> None
```

### UV mapping / unwrap / pack

```python
def alignUVIslands(occurrences: list[int], channel: int = 0, usePolygonsWeights: float = 0, useVerticesWeights: float = 0, alignmentMode: AlignmentMode = 0) -> None
def applyUvTransform(occurrences: list[int], matrix: list[list[float]], channel: int = 0) -> None
def automaticUVMapping(occurrences: list[int], channel: int = 0, maxAngleDistorsion: float = 0.5, maxAreaDistorsion: float = -1, sharpToSeam: bool = True, forbidOverlapping: bool = True, resolution: int = 1024, padding: int = 1) -> None
def copyUV(occurrences: list[int], sourceChannel: int = 0, destinationChannel: int = 0) -> None
def getRatioUV3D(occurrences: list[int], ratioMode: RatioUV3DMode, channel: int = 0) -> list[float]
def getUV3dRatio(occurrences: list[int]) -> float
def getUVQualityMetrics(occurrences: list[int], channel: int) -> dict
def getUvAabr(occurrences: list[int], channel: int = 0) -> geom.AABR
def hasOverlappingUV(occurrences: list[int], channel: int, resolution: int = 1024) -> bool
def mapUvOnAABB(occurrences: list[int], useLocalAABB: bool, uv3dSize: float, channel: int = 0, overrideExistingUVs: bool = True, ignoreScale: bool = True) -> None
def mapUvOnBox(occurrences: list[int], box: Box, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mapUvOnCubicAABB(occurrences: list[int], uv3dSize: float, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mapUvOnCustomAABB(occurrences: list[int], aabb: geom.AABB, uv3dSize: float, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mapUvOnCylinder(occurrences: list[int], cylinder: Cylinder, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mapUvOnFittingCylinder(occurrences: list[int], channel: int = 0, overrideExistingUVs: bool = True, useAABB: bool = True, forcedAxis: geom.Point3 = geom.Vector3(0,0,0)) -> None
def mapUvOnFittingSphere(occurrences: list[int], channel: int = 0, overrideExistingUVs: bool = True, useAABB: bool = True) -> None
def mapUvOnMBB(occurrences: list[int], useLocalMBB: bool, uv3dSize: float, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mapUvOnPlane(occurrences: list[int], plane: Plane, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mapUvOnSphere(occurrences: list[int], sphere: Sphere, channel: int = 0, overrideExistingUVs: bool = True) -> None
def mergeUVIslandsAffine(occurrences: list[int], channel: int = 0, scaleWeights: float = 0, maxScaleVariationFactor: float = 1.2, curvatureWeights: float = -1, usePolygonsWeights: float = 1, useVerticesWeights: float = -1, allowedTransformations: TransformationType = 0, allowUVInversion: bool = False, rotationStep: float = -1) -> None
def mergeUVIslandsRelaxed(occurrences: list[int], channel: int, targetIslandCount: int = 0, energyThreshold: float = 0.01, forceIsolatedFaces: bool = True) -> None
def normalizeUV(occurrences: list[int], sourceUVChannel: int, destinationUVChannel: int = -1, uniform: bool = True, sharedUVSpace: bool = True, ignoreNullIslands: bool = False) -> None
def removeUV(occurrences: list[int], channel: int = -1) -> None
def repackUV(occurrences: list[int], channel: int = 0, shareMap: bool = True, resolution: int = 1024, padding: int = 2, uniformRatio: bool = False, iterations: int = 3, removeOverlaps: bool = True) -> list[int]
def resizeUVsToTextureSize(occurrences: list[int], TextureSize: float, channel: int = 0) -> None
def scaleUV(occurrences: list[int], scaleU: float, scaleV: float, channel: int = 0) -> None
def splitUVForAtlas(occurrences: list[int]) -> None
def swapUvChannels(occurrences: list[int], firstChannel: int, secondChannel: int) -> None
def unwrapUV(occurrences: list[int], method: UnwrapUVMethod, channel: int = -1, createSeamsFromLoI: bool = False, iterMax: int = 50, tolerance: float = 0.00001) -> None
def getFittingCylinder(occurrences: list[int], useAABB: bool = True, forcedAxis: geom.Point3 = geom.Vector3(0,0,0)) -> geom.Affine
def getFittingSphere(occurrences: list[int], useAABB: bool = True) -> geom.Affine
```

### Texture baking — sessions and per-map bakers

```python
def beginBakingSession(destinationOccurrences: list[int], sourceOccurrences: list[int], uvChannel: int = 0, resolution: int = 1024, rayOffset: float = 0, rayMaxDist: float = -1, opacityThreshold: float = -1, useCurrentPosition: bool = False, shareMaps: bool = True, sourceElements: ElementFilter = 0) -> int
def beginVertexBakingSession(destinationOccurrences: list[int], sourceOccurrences: list[int], rayOffset: float = 0, rayMaxDist: float = -1, opacityThreshold: float = -1, useCurrentPosition: bool = False, sourceElements: ElementFilter = 0) -> int
def endBakingSession(sessionId: int) -> None
def setBakingSessionPadding(sessionId: int, padding: int) -> None
def fetchBakedMap(sessionId: int, x: int, y: int, mapId: int = 0) -> BakedValue
def fetchBakedVertex(sessionId: int, n: int, dstId: int = 0) -> BakedValue
def combineMaterials(occurrences: list[int], bakingOptions: BakeOption, overrideExistingUVs: bool = True, singularizeOnAO: bool = False) -> None
# AO bake into materials (high-level pattern, single call):
#   maps    = algo.BakeMaps(diffuse=False, normal=False, roughness=False,
#                           metallic=False, opacity=False,
#                           ambientOcclusion=True, emissive=False)
#   options = algo.BakeOption(resolution=1024, padding=2, textures=maps)
#   algo.combineMaterials([root], options,
#                         overrideExistingUVs=False,    # keep existing UVs
#                         singularizeOnAO=False)        # True to avoid AO bleed across instances
# After this call the AO image is wired into each material's `ao` slot
# (PBRMaterialInfos.ao / MaterialDefinition.ao). io.exportScene to .glb
# will embed the baked AO in the GLTF.

def bakeAOMap(sessionId: int, samples: int = 32, bentNormals: bool = False, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 0)) -> list[int]
def bakeDepthMap(sessionId: int, normalizeValue: float = 1.0, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeDiffuseMap(sessionId: int, withTransparency: bool = False, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeDisplacementMap(sessionId: int, normalize: bool = True, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeEmissiveMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeFeatureMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(1, 1, 1, 1)) -> list[int]
def bakeMaterialAOMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(1, 1, 1, 1)) -> list[int]
def bakeMaterialIdMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeMaterialPropertyMap(sessionId: int, propertyName: str, nComponents: int = 3, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeMetallicMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeNormalMap(sessionId: int, sourceSpace: Space = 2, destinationSpace: Space = 2, defaultColor: core.ColorAlpha = core.ColorAlpha(1, 1, 1, 1)) -> list[int]
def bakeOccurrencePropertyMap(sessionId: int, propertyName: str, nComponents: int = 3, defaultColor: core.ColorAlpha = core.ColorAlpha(1, 1, 1, 1)) -> list[int]
def bakeOpacityMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(1, 1, 1, 1)) -> list[int]
def bakePartIdMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakePositionMap(sessionId: int, local: bool = False, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeRoughnessMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0.5, 0.5, 0.5, 1)) -> list[int]
def bakeSpecularMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeUVMap(sessionId: int, uvChannel: int = 0, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeValidityMap(sessionId: int, validValue: float = 1., invalidValue: float = 0.) -> list[int]
def bakeVertexColorMap(sessionId: int, defaultColor: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 1)) -> list[int]
def bakeVertexAttributes(destinationOccurrences: list[int], sourceOccurrences: list[int], skinnedMesh: bool, positions: bool, useCurrentPositionAsTPose: bool = False) -> None
def bakeImpostor(occurrence: int, XFrames: int, YFrames: int, hemi: bool = False, resolution: int = 1024, padding: int = 0, roughness: bool = False, metallic: bool = False, ao: bool = False) -> OctahedralImpostor
def convertNormalMap(partOccurrences: list[int], normalMap: int, uvChannel: int = 0, sourceSpace: Space = 0, destinationSpace: Space = 2, sourceIsRightHanded: bool = True, destinationIsRightHanded: bool = True, replaceMap: bool = True, resolution: int = -1, padding: int = 1) -> int
def createBillboard(occurrences: list[int], resolution: int = 1024, XPositive: bool = True, XNegative: bool = True, YPositive: bool = True, YNegative: bool = True, ZPositive: bool = True, ZNegative: bool = True, moveFacesToCenter: bool = True, leftHandedNormalMap: bool = False) -> int
def fillNormalMap(normalMap: int) -> None
def orientNormalMap(normalMap: int) -> None
```

### Visibility / occlusion

```python
def createVisibilityInformation(occurrences: list[int], level: SelectionLevel, resolution: int, sphereCount: int, fovX: float = 90, considerTransparentOpaque: bool = False, root: int = 0, onHemisphereOnly: bool = False) -> None
def createVisibilityInformationAdvanced(occurrences: list[int], level: SelectionLevel, voxelSize: float, minimumCavityVolume: float, resolution: int, mode: InnerOuterOption = 0, considerTransparentOpaque: bool = False, root: int = 0) -> None
def createVisibilityInformationFromViewPoints(occurrences: list[int], cameraPositions: list[geom.Point3], cameraDirections: list[geom.Point3], cameraUps: list[geom.Point3], resolution: int, fovX: float = 90, considerTransparentOpaque: bool = False, root: int = 0) -> None
def findOccludedPartOccurrences(occurrences: list[int], resolution: int, sphereCount: int, fovX: float = 90, considerTransparentOpaque: bool = False, root: int = 0, onHemisphereOnly: bool = False) -> list[int]
def findOccludedPartOccurrencesAdvanced(occurrences: list[int], voxelSize: float, minimumCavityVolume: float, resolution: int, mode: InnerOuterOption = 0, considerTransparentOpaque: bool = False, root: int = 0) -> list[int]
def removeOccludedGeometries(occurrences: list[int], level: SelectionLevel, resolution: int, sphereCount: int, fovX: float = 90, considerTransparentOpaque: bool = False, adjacencyDepth: int = 1, occluders: list[int] = [], onHemisphereOnly: bool = False) -> list[bool]
def removeOccludedGeometriesAdvanced(occurrences: list[int], level: SelectionLevel, voxelSize: float, minimumCavityVolume: float, resolution: int, mode: InnerOuterOption = 0, considerTransparentOpaque: bool = False, adjacencyDepth: int = 1, occluders: list[int] = []) -> list[bool]
def removeOccludedGeometriesFromPoints(occurrences: list[int], level: SelectionLevel, positions: list[geom.Point3], resolution: int, sphereCount: int, fovX: float = 90, considerTransparentOpaque: bool = False, adjacencyDepth: int = 1, occluders: list[int] = []) -> list[bool]
def removeOccludedGeometriesFromViewPoints(occurrences: list[int], level: SelectionLevel, positions: list[geom.Point3], directions: list[geom.Point3], ups: list[geom.Point3], resolution: int, fovX: float = 90, considerTransparentOpaque: bool = False, adjacencyDepth: int = 1, occluders: list[int] = []) -> list[bool]
def createOcclusionMesh(occurrences: list[int], type: CreateOccluder, voxelSize: float, gap: int) -> int
def filterAO(...)  # see material module
def getVisibilityStats(occurrences: list[int]) -> dict
def createCavityOccurrences(occurrences: list[int], voxelSize: float, minimumCavityVolume: float, mode: InnerOuterOption = 0, parent: int = int()) -> int
```

### Voxelize / mesh-from-voxel reconstruction

```python
def voxelize(occurrences: list[int], voxelSize: float, elements: ElementFilter = 0, dilation: int = 0, useCurrentAnimationPosition: bool = False) -> int
def proxyMesh(occurrences: list[int], voxelSize: float, elements: ElementFilter = 0, dilation: int = 0, surfacic: bool = False) -> int
def marchingCubes(occurrences: list[int], voxelSize: float, elements: ElementFilter = 0, dilation: int = 0, surfacic: bool = False) -> int
def dualContouring(occurrences: list[int], filteringSize: float, voxelSize: float, tolerance: float, sameSizeOnAllAxis: bool) -> int
def retopologize(occurrences: list[int], targetTriangleCount: int, pureQuad: bool, pointCloud: bool, precision: float = -1) -> int
def convexDecomposition(occurrences: list[int], maxCount: int, vertexCount: int, approximate: bool, resolution: int = 100000, concavity: float = 0.001) -> list[int]
```

### Replace / saw / explode

```python
def replaceBy(occurrences: list[int], replaceBy: list) -> None
def replaceByBox(occurrences: list[int], boxType: ReplaceByBoxType) -> None
def replaceByConvexHull(occurrences: list[int]) -> None
def replaceByPrimitive(occurrences: list[int], primitive: list, generateUV: bool = True) -> None
def sawWithAABB(occurrences: list[int], aabb: geom.AABB, mode: SawingMode, innerSuffix: str = "_inner", outerSuffix: str = "_outer") -> None
def sawWithOBB(occurrences: list[int], obb: geom.OBB, mode: SawingMode, innerSuffix: str = "_inner", outerSuffix: str = "_outer") -> None
def sawWithOctree(occurrences: list[int], aabb: geom.AABB, maxDepth: int, maxTrianglesByLeaf: int = -1, sawTolerance: float = 0) -> int
def sawWithPlane(occurrences: list[int], planeOrigin: geom.Point3, planeNormal: geom.Point3, mode: SawingMode, innerSuffix: str = "_inner", outerSuffix: str = "_outer", tolerance: float = 0) -> None
def explodeBodies(occurrences: list[int], groupOpenShells: bool = False) -> None
def explodeByMaterials(occurrences: list[int]) -> None
def explodeByTopoDimension(occurrences: list[int]) -> list[int]
def explodeByVertexCount(occurrences: list[int], maxVertexCount: int, maxTriangleCount: int, countMergedVerticesOnce: bool = True) -> None
def explodeByVoxel(occurrences: list[int], voxelSize: float) -> None
def explodeConnectedMeshes(occurrences: list[int], explodeNonManifoldEdges: bool = False) -> None
def explodePatches(occurrences: list[int]) -> None
```

### Instance similarity

```python
def convertSimilarPartOccurrencesToInstances(occurrences: list[int], checkMeshTopo: bool, checkVertexPositions: bool, vertexPositionPrecision: int, checkUVTopo: bool, checkUVVertexPositions: bool, UVPositionprecision: int) -> None
def convertSimilarPartOccurrencesToInstancesFast(occurrences: list[int], dimensionsSimilarity: float, polycountSimilarity: float, ignoreSymmetry: bool) -> None
def findSimilarPartOccurrencesFast(occurrences: list[int], dimensionsSimilarity: float, polycountSimilarity: float, ignoreSymmetry: bool) -> list[int]
```

### Vertex weights / visibility attributes

```python
def createVertexWeightsFromVertexColors(occurrences: list[int], offset: float = 0, scale: float = 1, strategy: VertexWeightStrategy = 0) -> None
def createVertexWeightsFromVisibilityAttributes(occurrences: list[int], offset: float = 0, scale: float = 1) -> None
def deleteVertexWeights(occurrences: list[int]) -> None
def createVisibilityAttributes(occurrences: list[int]) -> None
def deleteVisibilityAttributes(occurrences: list[int]) -> None
def deletePolygonalWeightAttribute(occurrences: list[int]) -> None
def flagVisibilityAttributesOnTransparents(occurrences: list[int]) -> None
def transferVisibilityToPolygonalWeight(occurrences: list[int], Mode: VisibilityToWeightMode) -> None
```

---

## `pxz.geom`

Geometry primitives and matrix math.

### Classes

```python
class AABB / AABR / OBB / ExtendedBox
class Affine
class CameraCalibration / Curvatures
class Point2 / Point3 / Point4
class Vector4I
class Ray
class Axis(IntEnum) / AxisPlane(IntEnum)
```

### Functions

```python
def applyTransform(entity: int, matrix: list[list[float]]) -> None
def getEntityAABB(entity: int) -> AABB
def changeOfBasisMatrix(origin: Point3, x: Point3, y: Point3, z: Point3) -> list[list[float]]
def decomposeTransform(matrix: list[list[float]]) -> dict
def fromAffine(affine: Affine) -> list[list[float]]
def fromLookAtMatrix(matrix: list[list[float]], distanceFromTarget: float = 1) -> dict
def fromOriginNormal(origin: Point3, normal: Point3) -> list[list[float]]
def fromTRS(T: Point3, R: Point3, S: Point3) -> list[list[float]]
def toTRS(matrix: list[list[float]]) -> list[Point3]
def getMaxScale(matrix: list[list[float]]) -> float
def invertMatrix(matrix: list[list[float]]) -> list[list[float]]
def lookAtMatrix(position: Point3, up: Point3, target: Point3) -> list[list[float]]
def matrixToQuaternion(matrix: list[list[float]]) -> Point4
def quaternionToMatrix(quaternion: Point4) -> list[list[float]]
def multiplyMatrices(left: list[list[float]], right: list[list[float]]) -> list[list[float]]
def multiplyMatrixPoint(matrix: list[list[float]], point: Point3) -> Point3
def multiplyMatrixVector(matrix: list[list[float]], vector: Point3) -> Point3
def orthographicMatrix(width3D: float, height3D: float, nearClipDistance: float, farClipDistance: float) -> list[list[float]]
def perspectiveMatrix(fovX: float, aspectRatio: float, nearClipDistance: float, farClipDistance: float) -> list[list[float]]
```

---

## `pxz.view`

GPU viewer + offline rendering. Used for screenshots in headless scripts.

### Notable classes / enums

```python
class CameraType(IntEnum)             # Perspective / Orthographic
class GraphicAPI(IntEnum)
class GraphicsContext
class PrimitiveSelectionType(IntEnum)
class RateControl(IntEnum)
class RenderMap(IntEnum)
class QP
class EncoderSettings / StreamedViewerInfo / WebRTCInfo
class AnimationPlayerInfo
```

### Context

```python
def destroyContext() -> None
def suitableGPUAvailable() -> bool
```

### GPU scenes

```python
def createGPUScene(roots: list[int], constructEdges: bool = False, useIsolate: bool = True) -> int
def destroyGPUScene(scene: int) -> None
def addGPUScene(scene: int, viewer: int = -1) -> None
def removeGPUScene(scene: int, viewer: int = -1) -> None
def getGlobalGPUScene() -> int
def getLastAABB(scene: int, viewer: int) -> geom.AABB
def getOccurrenceIndex(occurrence: int, scene: int) -> int
def getSceneIndex(scene: int, viewer: int) -> int
def lockGPUSceneUpdate(scene: int) -> None
def lockGPUScenesUpdate(scenes: list[int]) -> None
def tryLockGPUSceneUpdate(scene: int) -> bool
def tryLockGPUScenesUpdate(scenes: list[int]) -> list[bool]
def unlockGPUSceneUpdate(scene: int) -> None
def unlockGPUScenesUpdate(scenes: list[int]) -> None
```

### Viewers

```python
def createViewer(width: int, height: int, sharedContext: GraphicsContext = view.GraphicsContext(), nbViews: int = 1) -> int
def destroyViewer(viewer: int) -> None
def resizeViewer(width: int, height: int, viewer: int = -1) -> None
def refreshViewer(viewer: int = -1) -> None
def setDefaultViewerId(viewer: int) -> None
def getViewerSize(viewer: int = -1) -> dict
def getViewerStats(viewer: int = -1) -> dict
def getViewerProperty(propertyName: str, viewer: int = -1) -> str
def getViewerPropertyInfo(propertyName: str, viewer: int = -1) -> core.PropertyInfo
def listViewerProperties(viewer: int = -1) -> list[core.PropertyInfo]
def setViewerProperty(propertyName: str, propertyValue: str, viewer: int = -1) -> None
```

Common viewer properties: `"OcclusionCullingEnabled"`, `"ShowEdges"`, `"ShowLines"`, `"EnableToneMaping"`, `"UseFXAA"`, `"UseSSAO"` — pass values as strings (`"True"` / `"False"`).

### Camera

```python
def fitCamera(direction: geom.Point3, cameraType: CameraType = 1, fov: float = 90, viewer: int = -1, fitToOccurrences: list[int] = []) -> None
def getCameraFrontAxis(viewer: int = -1, matrixIndex: int = 0) -> geom.Point3
def getCameraPosition(viewer: int = -1, matrixIndex: int = 0) -> geom.Point3
def getCameraRightAxis(viewer: int = -1, matrixIndex: int = 0) -> geom.Point3
def getCameraUpAxis(viewer: int = -1, matrixIndex: int = 0) -> geom.Point3
def getAutoClipping(viewer: int, cameraPos: geom.Point3) -> geom.Point2
def getViewerMatrices(viewer: int = -1) -> dict
def setViewerMatrices(views: list[list[list[float]]], projs: list[list[list[float]]], clipping: geom.Point2, viewer: int = -1) -> None
def drawCappingPlane(cuttingPlane: int) -> int
```

### Picking / primitive selection

```python
def pick(x: int, y: int, viewer: int = -1) -> dict
def pickRectangle(xMin: int, xMax: int, yMin: int, yMax: int, viewer: int = -1, inDepth: bool = False) -> list[int]
def selectPrimitives(xMin: int, xMax: int, yMin: int, yMax: int, primitiveType: PrimitiveSelectionType, viewer: int = -1) -> None
def unselectPrimitives(xMin: int, xMax: int, yMin: int, yMax: int, primitiveType: PrimitiveSelectionType, viewer: int = -1) -> None
def invertSelectPrimitives(xMin: int, xMax: int, yMin: int, yMax: int, primitiveType: PrimitiveSelectionType, viewer: int = -1) -> None
def identifySelectedEdges(scene: int) -> None
def visibilityShoot(viewer: int = -1, parts: bool = True, patches: bool = True, polygons: bool = True, countOnce: bool = False) -> list[int]
```

### Screenshots / image extraction

```python
def takeScreenshot(fileName: str, viewer: int) -> None
def getCompositedImage(viewer: int) -> material.ImageDefinition
def getRenderMapImage(viewer: int, renderMap: RenderMap) -> material.ImageDefinition
def getD3D11Texture(renderMap: RenderMap, viewer: int = -1) -> core.Ptr
def getGLTextureHandle(renderMap: RenderMap, viewer: int = -1) -> int
def getVulkanTexture(renderMap: RenderMap, viewer: int = -1) -> core.Ptr
```

### Streamed viewers / recording

```python
def createStreamedViewer(width: int, height: int, encoderSettings: EncoderSettings = EncoderSettings(), useWebRTC: bool = False, webRTCInfo: WebRTCInfo = WebRTCInfo()) -> StreamedViewerInfo
def resizeStreamedViewer(width: int, height: int, viewer: int = -1, encoderSettings: EncoderSettings = EncoderSettings()) -> None
def startRecording(filePath: str, viewer: int, encoderSettings: EncoderSettings = EncoderSettings()) -> None
def stopRecording(viewer: int) -> None
```

### Animation playback (in viewer)

```python
def playAnimation(animation: int, speed: float = 1, loop: bool = False) -> None
def pauseAnimation(animation: int) -> None
def resumeAnimation(animation: int) -> None
def stopAnimation(animation: int, applyDefault: bool = True) -> None
def pauseAllAnimation() -> None
def resumeAllAnimation() -> None
def stopAllAnimation(applyDefault: bool = True) -> None
def setAnimationFrame(animation: int, frame: int) -> None
def setAnimationLoop(animation: int, loop: bool) -> None
def setAnimationSpeed(animation: int, speed: float) -> None
def isAnimationPlaying(animation: int) -> bool
def applyPlayingAnimations(time: int) -> None
def getAnimationPlayerInfo(animation: int) -> AnimationPlayerInfo
```

### Callbacks

`addAfterFramebufferCreate`, `addBeforeFramebufferDelete`, `addAfter/BeforeViewerPropertyChanged`, `addAnimationPaused/Stopped`, `addAnimationPlayed/Resumed`, `addAnimationPlayingStatusChanged` — each with a `removeXxxCallback(id)` partner.

---

## `pxz.material`

Materials, images/textures, shader patterns.

### Notable classes / enums

```python
class MaterialPatternType(IntEnum)
class ImageChangeType(IntEnum) / ImageComponentType(IntEnum) / ImageLayout(IntEnum)
class MaterialChangeType(IntEnum)
class BlurFilter(IntEnum) / EdgeFilter(IntEnum) / ResizeFilterMethod(IntEnum)
class ShaderUniformType(IntEnum)
class ImageDefinition / MaterialDefinition / MaterialFromMapsReturn
class ColorMaterialInfos / ImpostorMaterialInfos / PBRMaterialInfos / StandardMaterialInfos / UnlitTextureMaterialInfos
class PixelInfo / RoI
class Texture / TextureSampler
```

### Materials

```python
def getAllMaterials() -> list[int]
def createMaterial(name: str, pattern: str, addToMaterialLibrary: bool = True) -> int
def createMaterialFromDefinition(materialDefinition: MaterialDefinition) -> int
def createMaterialsFromDefinitions(materialDefinitions: list[MaterialDefinition]) -> list[int]
def createMaterialsFromMaps(directory: str) -> MaterialFromMapsReturn
def copyMaterial(toCopy: int, addToMaterialLibrary: bool) -> int
def clearAllMaterials() -> None
def makeMaterialNamesUnique(materials: list[int] = []) -> None
def findMaterialsByPattern(pattern: str) -> list[int]
def findMaterialsByProperty(propertyName: str, propertyValue: str, caseInsensitive: bool = False) -> list[int]
def isOpaque(material: int) -> bool
def areOpaques(materials: list[int]) -> list[bool]
def getMaterialDefinition(material: int) -> MaterialDefinition
def getMaterialDefinitions(materials: list[int]) -> list[MaterialDefinition]
def getMaterialPattern(material: int) -> str
def getMaterialPatternType(material: int) -> MaterialPatternType
def setMaterialPattern(material: int, pattern: str) -> None
def getMaterialMainColor(material: int) -> core.ColorAlpha
def setMaterialMainColor(material: int, color: core.ColorAlpha) -> None
def getColorMaterialInfos(material: int) -> ColorMaterialInfos
def getImpostorMaterialInfos(material: int) -> ImpostorMaterialInfos
def getPBRMaterialInfos(material: int) -> PBRMaterialInfos
def setPBRMaterialInfos(material: int, infos: PBRMaterialInfos) -> None
def getStandardMaterialInfos(material: int) -> StandardMaterialInfos
def getUnlitTextureMaterialInfos(material: int) -> UnlitTextureMaterialInfos
def setCoeffOrTextureProperty(material: int, name: str, coeffOrTexture: list) -> None
def setColorAlphaProperty(material: int, name: str, color: core.ColorAlpha) -> None
def setColorOrTextureProperty(material: int, name: str, colorOrTexture: list) -> None
```

### Custom shader patterns

```python
def createCustomMaterialPattern(name: str) -> int
def findCustomMaterialPatternByName(name: str) -> int
def getAllMaterialPatterns() -> list[str]
def getCustomMaterialPattern(material: int) -> int
def setFragmentShader(pattern: int, code: str) -> None
def setVertexShader(pattern: int, code: str) -> None
def addUniformProperty(pattern: int, name: str, type: ShaderUniformType) -> None
def getUniformPropertyType(pattern: int, name: str) -> ShaderUniformType
```

### Color helpers / text

```python
def generateColorFromIndex(index: int) -> core.Color
def generateUniqueColors(count: int) -> list[core.Color]
def getPointsAndMaterialFromText(text: str, fontName: str, fontSize: int, matrix: list[list[float]], colorInput: core.Color, offset: float = 0.0, height3D: float = 0.0) -> dict
```

### Images / textures

```python
def importImage(filename: str) -> int
def exportImage(image: int, filename: str) -> None
def getImportImageFormats() -> list[core.Format]
def getExportImageFormats() -> list[core.Format]
def getAllImages(materials: list[int] = []) -> list[int]
def createImageFromData(data: list[core.Byte], name: str = "img") -> int
def createImageFromDefinition(imageDefinition: ImageDefinition) -> int
def createImagesFromDefinitions(imageDefinitions: list[ImageDefinition]) -> list[int]
def createCheckerboardImage(width: int, height: int, cellSize: int, color1: core.ColorAlpha = core.ColorAlpha(0, 0, 0, 0), color2: core.ColorAlpha = core.ColorAlpha(1, 1, 1, 1), layout: ImageLayout = 6, type: ImageComponentType = 1) -> int
def getImageDefinition(image: int) -> ImageDefinition
def getImageDefinitions(images: list[int]) -> list[ImageDefinition]
def updateImageFromDefinition(image: int, imageDefinition: ImageDefinition) -> None
def updateImagesFromDefinitions(image: list[int], imageDefinitions: list[ImageDefinition]) -> None
def convertImage(image: int, layout: ImageLayout, type: ImageComponentType, inPlace: bool = False) -> int
def convertImageToDefinition(image: int, layout: ImageLayout, type: ImageComponentType) -> ImageDefinition
def convertFloat32To8BitsImage(image32F: int, minValue: float = -1, maxValue: float = 1, inPlace: bool = False) -> int
def convertHeightMapToNormalMap(hmap: int, height: float = 0.5) -> int
def overrideImageFormat(image: int, layout: ImageLayout = 0, type: ImageComponentType = 0) -> bool
def extractImageChannels(image: int, channel: int = -1) -> list[int]
def extractImageComponents(image: int, components: ImageLayout) -> list[int]
def applyFactorOnImage(image: int, imageIsLinear: bool, factor: core.ColorAlpha) -> None
def blurImage(image: int, radius: int, blurType: BlurFilter, edgeFilter: EdgeFilter) -> None
def fillImageWithColor(image: int, color: core.ColorAlpha, x: int = 0, y: int = 0, w: int = -1, h: int = -1) -> None
def fillUnusedPixels(image: int, unusedColor: core.ColorAlpha = core.ColorAlpha(0., 0., 0., 0.), size: int = -1, validityMask: int = 0, inPlace: bool = False) -> int
def filterAO(aoMaps: list[int], normalMaps: list[int], sigmaPos: float = 2.0, sigmaValue: float = 0.2, sigmaNormal: float = 0.2, levelCount: int = 4, filterLowValues: bool = True, lowValueThreshold: float = 0.01) -> list[int]
def flipImageY(image: int) -> None
def getImageAverageColor(image: int) -> dict
def getImageColorBilinear(image: int, x: float, y: float, edgeFilter: EdgeFilter = 0) -> core.ColorAlpha
def getImageColorRange(image: int) -> list[core.ColorAlpha]
def getImageComponentType(image: int) -> ImageComponentType
def getImageComponentTypeName(type: ImageComponentType) -> str
def getImageFormatName(layout: ImageLayout, type: ImageComponentType) -> str
def getImageLayout(image: int) -> ImageLayout
def getImagePixelColor(image: int, x: int, y: int) -> core.ColorAlpha
def getImagePixelInfo(image: int) -> PixelInfo
def getImagePixelInfoFromDefinition(imageDefinition: ImageDefinition) -> PixelInfo
def getImagePixelInfoFromLayoutAndType(layout: ImageLayout, type: ImageComponentType) -> PixelInfo
def getImageRoI(image: int) -> RoI
def getImageSize(image: int) -> dict
def getImagesSizes(images: list[int]) -> dict
def getSubImage(image: int, x: int, y: int, w: int, h: int) -> int
def setSubImage(destination: int, subImage: int, x: int, y: int, edgeFilter: EdgeFilter = 0) -> None
def invertImageColor(image: int) -> None
def remapIndexMap(maps: list[int], maxIndices: int) -> dict
def resizeImage(image: int, width: int, height: int, filteringMethod: ResizeFilterMethod = 0) -> None
def rotateImage(image: int, angle: float, cx: float, cy: float, edgeFilter: EdgeFilter = 0, adjustSize: bool = False) -> None
def stretchImage(image: int, sx: float, sy: float, cx: float, cy: float, edgeFilter: EdgeFilter = 0, adjustSize: bool = False) -> None
def transformImage(image: int, matrix: list[list[float]], edgeFilter: EdgeFilter = 0, adjustSize: bool = False) -> None
def translateImage(image: int, tx: float, ty: float, edgeFilter: EdgeFilter = 0, adjustSize: bool = False) -> None
def setImageRoI(image: int, x: int, y: int, w: int, h: int) -> None
def clearImageRoI(image: int) -> None
```

### Material user data

`getMaterialUserData` / `setMaterialUserData` / `hasMaterialUserData` / `unsetMaterialUserData` / `subscribeToMaterialUserData` / `unsubscribeFromMaterialUserData` and the multi-material variants.

### Callbacks

`addImageChangedCallback`, `addMaterialChangedCallback`, with matching `removeXxx`.

---

## `pxz.polygonal`

Mesh-level definitions, Draco compression, mesh / UV checksums.

### Classes

```python
class MeshDefinition
class Submesh
class StyleType(IntEnum) / StylizedLine
class TopologyCategoryMask
class TopologyConnectivityMask(IntEnum) / TopologyDimensionMask(IntEnum)
```

### Functions

```python
def getPolygonCount(mesh: int, asTriangleCount: bool = False) -> int
def computeMeshTopoChecksum(mesh: int) -> str
def computeMeshVertexPositionsChecksum(mesh: int, precisionFloat: int = -1) -> str
def computeUVTopoChecksum(mesh: int, uvChannel: int) -> str
def computeUVVertexPositionsChecksum(mesh: int, uvChannel: int, precisionFloat: int = -1) -> str
def dracoEncode(mesh: int, compressionLevel: int = 7, quantizationPosition: int = -1, quantizationNormal: int = -1, quantizationTexCoord: int = -1) -> dict
def dracoDecode(buffer: list[core.Byte], jointIndicesId: int = -1, jointWeightsId: int = -1) -> int
def createMeshFromDefinition(meshDefinition: MeshDefinition) -> int
def createMeshFromDefinitions(meshDefinition: list[MeshDefinition]) -> int
def createMeshesFromDefinitions(meshDefinitions: list[MeshDefinition]) -> list[int]
def createMeshFromText(text: str, matrix: list[list[float]], font: str = "ChicFont", fontSize: int = 64, color: core.ColorAlpha = core.ColorAlpha(), heigth3D: float = 40) -> dict
def getMeshDefinition(mesh: int) -> MeshDefinition
def getMeshDefinitions(meshes: list[int]) -> list[MeshDefinition]
def getMeshSkinning(mesh: int) -> dict
def setMeshSkinning(mesh: int, joints: list[int], IBMs: list[list[list[float]]]) -> None
def hasMeshJoints(mesh: int) -> bool
def hasUVs(mesh: int, channel: int = -1) -> bool
def hasNormalizedUVs(mesh: int, channel: int) -> bool
def createJointPlaceholders(data: list[int], worldMatrices: list[list[list[float]]]) -> list[int]
def getJointPlaceholders(joints: list[int]) -> list[int]
def usePointGapFillerNormal(points: list[geom.Point3], normals: list[geom.Point3]) -> list[int]
```

---

## `pxz.cad`

Exact BRep (boundary-representation) modeling: curves, surfaces, topology (vertices/edges/coedges/loops/faces/shells/bodies), booleans on solids, and BRep primitives. **Niche** — most CAD *prep* (import, repair, tessellate, optimize) lives in `algo`/`io`/`scene`; reach for `cad` only when constructing or interrogating exact geometry.

Everything here is an integer handle. BRep entities live in a **thread BRep session** for construction workflows (`startThreadBrepSession` / `endThreadBrepSession`).

### Notable classes / enums

```python
class Bounds1D                       # 1D parametric range (curves)
class Bounds2D                       # 2D parametric range (surfaces)
class BrickDefinition
class BrickType(IntEnum)
class ExtrusionBoundaryType(IntEnum) # default 0 in extrusion functions
class OrientedEdge
class OrientedFace
class ProfileLoop                    # profileBase / profileEnd elements for extrusions
class SplittedEdge
class TorusType(IntEnum)
```

### Configuration / units

```python
def getPrecision() -> float
def getUnitLength() -> float
def setUnitLength(precision: float) -> None
def configureFunctionLogger(functionName: str, enableFunction: bool, enableParameters: bool, enableExecutionTime: bool) -> None
```

### Boolean operators (on solids/bodies)

```python
def solidIntersection(A: int, B: int) -> list[int]
def solidSubtraction(A: int, B: int) -> list[int]
def solidUnion(A: int, B: int) -> list[int]
```

### Curve creation

```python
def createBezierCurve(poles: list[geom.Point3]) -> int
def createCircleCurve(radius: float, matrix: list[list[float]]) -> int
def createCompositeCurve(CurveList: list[int]) -> int
def createCosinusCurve(Amplitude: float, Offset: float, Period: float, matrix: list[list[float]]) -> int
def createEllipseCurve(URadius: float, VRadius: float, matrix: list[list[float]]) -> int
def createHelixCurve(radius: float, pitch: float, matrix: list[list[float]], trigonometrixOrientation: bool = True) -> int
def createHermiteCurve(FirstPoint: geom.Point3, FirstTangent: geom.Point3, SecondPoint: geom.Point3, SecondTangent: geom.Point3) -> int
def createHyperbolaCurve(URadius: float, VRadius: float, matrix: list[list[float]]) -> int
def createIntersectionCurve(firstSurface: int, secondSurface: int, chart: int, minBounds: float, maxBounds: float) -> int
def createLineCurve(OriginPt: geom.Point3, DirectionPt: geom.Point3) -> int
def createNURBSCurve(degree: int, knots: list[float], poles: list[geom.Point3], weights: list[float] = []) -> int
def createParabolaCurve(focalLength: float, matrix: list[list[float]]) -> int
def createPolylineCurve(points: list[geom.Point3], parameters: list[float] = []) -> int
def createSegmentCurve(firstPoint: geom.Point3, secondPoint: geom.Point3) -> int
def createSurfacicCurve(surface: int, curve2D: int) -> int
def createTransformedCurve(curve: int, matrix: list[list[float]]) -> int
def invertCurve(curve: int, precision: float) -> int
```

### Extrusion creation

```python
def createBoundedLinearExtrusion(direction: geom.Point3, planeOrigin: geom.Point3, planeNormal: geom.Point3, profileBase: list[ProfileLoop], startingNormal: geom.Point3, boundaryType: ExtrusionBoundaryType = 0, profileEnd: list[ProfileLoop] = []) -> int
def createCurveExtrusion(curve: int, profileBase: list[ProfileLoop], startingNormal: geom.Point3, boundaryType: ExtrusionBoundaryType = 0, profileEnd: list[ProfileLoop] = []) -> int
def createLinearExtrusion(direction: geom.Point3, depth: float, profileBase: list[ProfileLoop], startingNormal: geom.Point3, boundaryType: ExtrusionBoundaryType = 0, profileEnd: list[ProfileLoop] = []) -> int
def createMultiExtrusion(profileBaseList: list[list[ProfileLoop]], profileExtrusionList: list[list[int]], boundaryType: ExtrusionBoundaryType = 0) -> int
def createRevolveExtrusion(center: geom.Point3, axis: geom.Point3, angle: float, profileBase: list[ProfileLoop], startingNormal: geom.Point3, boundaryType: ExtrusionBoundaryType = 0, profileEnd: list[ProfileLoop] = []) -> int
```

### Surface creation

```python
def createBezierSurface(degreeU: int, degreeV: int, poles: list[geom.Point3]) -> int
def createConeSurface(radius: float, semiAngle: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createCurveExtrusionSurface(generatrixCurve: int, directrixCurve: int, refSurface: int = 0) -> int
def createCylinderSurface(radius: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createEllipticConeSurface(radius1: float, radius2: float, semiAngle: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createNURBSSurface(degreeU: int, degreeV: int, knotsU: list[float], knotsV: list[float], poles: list[geom.Point3], weights: list[float] = []) -> int
def createOffsetSurface(baseSurface: int, distance: float) -> int
def createPlaneSurface(matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createRevolutionSurface(generatrixCurve: int, axisOrigin: geom.Point3, axisDirection: geom.Point3, startParam: float = 0, endParam: float = 6.283185) -> int
def createRuledSurface(firstCurve: int, secondCurve: int) -> int
def createSphereSurface(radius: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createTabulatedCylinderSurface(directrixCurve: int, GeneratixLine: geom.Point3, minRange: float, maxRange: float) -> int
def createTorusSurface(radiusMax: float, radiusMin: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def addPrecisionArea(surface: int, aabr: geom.AABR) -> None
def needPrecisionArea(surface: int) -> bool
```

### Topology construction (vertices → edges → loops → faces → shells → bodies)

```python
def createVertex(position: geom.Point3) -> int
def createEdge(curve: int, startVertex: int, endVertex: int) -> int
def createEdgeFromCurve(curve: int) -> int
def createEdgeWithBounds(curve: int, startVertex: int, endVertex: int, bounds: Bounds1D) -> int
def createCoEdge(edge: int, orientation: bool, surface: int = 0, curve2D: int = 0, computeGateway: bool = False) -> int
def createLoop(coEdges: list[int], check: bool = True, deleteIsolatedVertices: bool = True) -> int
def createLoopFromCurve(curve: int) -> int
def createFace(surface: int, loopList: list[int] = [], useSurfaceOrientation: bool = False) -> int
def createOpenShell(faces: list[int], orientations: list[bool]) -> int
def createClosedShell(faces: list[int], orientations: list[bool]) -> int
def createBody(outerShell: int, innerShells: list[int] = []) -> int
def buildFaces(surface: int, loopList: list[int]) -> dict
def invertCoEdge(coedge: int) -> None
def invertFaces(faces: list[int], invertLoops: bool = True) -> None
def invertLoop(loop: int) -> None
def setCoEdgeCurve2D(coEdge: int, curve2D: int) -> None
def setCoEdgeSurface(coEdge: int, surface: int) -> None
def setCurveLimits(curve: int, limits: Bounds1D) -> None
```

### BRep primitives

```python
def createBRepCone(radius: float, height: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createBRepCube(size: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createBRepCylinder(radius: float, length: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createBRepPlane(length: float, width: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createBRepSphere(radius: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
def createBRepTorus(majorRadius: float, minorRadius: float, matrix: list[list[float]] = geom.IdentityMatrix4) -> int
```

### Model management / thread BRep session

```python
def createModel(precision: float = -1) -> int
def addBodyToModel(body: int, model: int) -> None
def addEdgeToModel(edge: int, model: int) -> None
def addOpenShellToModel(shell: int, model: int) -> None
def addVertexToModel(vtx: int, model: int) -> None
def getAllModelFaces(model: int) -> list[int]
def getModelBodies(model: int) -> list[int]
def getModelBoundaries(model: int) -> list[list[int]]
def getModelEdges(model: int) -> list[int]
def getModelOpenShells(model: int) -> list[int]
def getModelPrecision(model: int) -> float
def getModelVertices(model: int) -> list[int]
def getReferencers(entity: int) -> list[int]
def startThreadBrepSession(precision: float) -> None
def endThreadBrepSession() -> None
```

### Materials on faces/edges

```python
def getFaceMaterial(face: int) -> int
def setFaceMaterial(face: int, material: int) -> None
def getEdgeMaterial(edge: int) -> int
def setEdgeMaterial(edge: int, material: int) -> None
```

### Evaluation / projection / inversion

```python
def evalOnCurve(curve: int, parameter: float, derivation: int = 0) -> dict
def evalOnSurface(surface: int, parameter: geom.Point2, derivation: int = 0) -> dict
def evalCurvatureOnCurve(curve: int, parameter: float) -> float
def evalCurvatureOnSurface(surface: int, parameter: geom.Point2) -> geom.Curvatures
def projectOnCurve(curve: int, point: geom.Point3, precision: float = -1) -> float
def projectOnSurface(surface: int, point: geom.Point3, precision: float = -1) -> geom.Point2
def invertOnCurve(curve: int, point: geom.Point3, precision: float = -1) -> float
def invertOnSurface(surface: int, point: geom.Point3, precision: float = -1) -> geom.Point2
def getParametricPrecisionOnSurface(surface: int, precision: float) -> float
```

### Queries — curves / surfaces / topology

```python
def areCurvesEquals(curve1: int, curve2: int) -> bool
def getCurveLength(curve: int) -> float
def getCurveLimits(curve: int) -> Bounds1D
def isCurveClosed(curve: int) -> bool
def isCurveFinite(curve: int) -> bool
def isCurvePeriodic(curve: int) -> dict
def getSurfaceLimits(surface: int) -> Bounds2D
def getSurfaceType(surface: int) -> int
def isSurfaceClosed(surface: int) -> dict
def isSurfaceFinite(surface: int) -> bool
def isSurfacePeriodic(surface: int) -> dict
def needTorusShapeCheck(surface: int, points: list[geom.Point3]) -> bool
def getEdgeConnectivity(edge: int) -> int
def getEdgeLength(edge: int) -> float
def getVertexPosition(vertex: int) -> geom.Point3
def getLoopCoEdges(loop: int) -> list[int]
def getBodyClosedShells(body: int) -> list[int]
def getClosedShellOrientedFaces(closedShell: int) -> list[OrientedFace]
def getOpenShellOrientedFaces(openShell: int) -> list[OrientedFace]
def getFaceParametricBoundaries(face: int) -> list[list[geom.Point2]]
```

### Definition getters (return `dict` unless noted)

`getCircleCurveDefinition`, `getCoEdgeDefinition`, `getCompositeCurveDefinition`, `getConeSurfaceDefinition`, `getCurveExtrusionSurfaceDefinition`, `getCylinderSurfaceDefinition`, `getEdgeDefinition`, `getEllipseCurveDefinition`, `getEllipticConeSurfaceDefinition`, `getFaceDefinition`, `getHelixCurveDefinition`, `getHermiteCurveDefinition`, `getHyperbolaCurveDefinition`, `getIntersectionCurveDefinition`, `getLineCurveDefinition`, `getNURBSCurveDefinition`, `getNURBSSurfaceDefinition`, `getOffsetCurveDefinition`, `getOffsetSurfaceDefinition`, `getParabolaCurveDefinition`, `getPolylineCurveDefinition`, `getRevolutionSurfaceDefinition`, `getRuledSurfaceDefinition`, `getSegmentCurveDefinition`, `getSphereSurfaceDefinition`, `getSurfacicCurveDefinition`, `getTabulatedCylinderSurfaceDefinition`, `getTorusSurfaceDefinition`, `getTransformedCurveDefinition` — each `(entity: int) -> dict`. Exceptions: `getPlaneSurfaceDefinition(planeSurface: int) -> list[list[float]]`.

---

## `pxz.raytrace`

Offline ray-traced still rendering. One class, one render call.

### Class

```python
class Camera:
    position: geom.Point3
    direction: geom.Point3
    up: geom.Point3
    fov: float
    def __init__(self, position: geom.Point3, direction: geom.Point3, up: geom.Point3, fov: float) -> None
```

### Functions

```python
def renderImage(width: int, height: int, camera: Camera, outputImagePath: str) -> None
def configureFunctionLogger(functionName: str, enableFunction: bool, enableParameters: bool, enableExecutionTime: bool) -> None
```

> For fast GPU screenshots/turntables prefer `pxz.view` (`view.takeScreenshot`, offscreen viewers). Use `raytrace.renderImage` only when you specifically need ray-traced image quality.
