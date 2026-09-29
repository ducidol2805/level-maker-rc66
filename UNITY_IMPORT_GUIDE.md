# Import map Racblox vao Unity

Tai lieu nay dung cho file JSON tao boi **File > Export Game JSON** trong
Racblox. Importer ben duoi hoat dong voi Built-in Render Pipeline va URP.

## 1. Du lieu Racblox export

File game JSON co dang:

```json
{
  "pieces": [
    {
      "id": "blk_001",
      "pos": [2, 3, 0],
      "rot": 90,
      "color": 4
    }
  ]
}
```

- `id`: ID cua piece, trung voi truong `id` trong `library/**/piece.json`.
- `pos`: toa do o luoi `[x, y, z]`.
- `rot`: goc xoay quanh truc Y, tinh bang do.
- `color`: ID mau tu 0 den 31.

Racblox va Unity cung dung X sang phai, Y huong len va Z theo chieu sau. Khong
can doi truc. `rot` duoc gan truc tiep bang `Quaternion.Euler(0, rot, 0)`.

## 2. Chuan bi asset trong Unity

Tao cau truc goi y:

```text
Assets/
  Racblox/
    Models/            <- copy toan bo file FBX tu thu muc models/
    Levels/            <- dat file JSON export tai day
    Materials/
    Scripts/
```

1. Copy toan bo `models/ARC`, `models/BLK`, `models/CYL`, `models/RMP` va
   `models/TAL` cua project Racblox vao `Assets/Racblox/Models/`.
2. Copy file JSON da export vao `Assets/Racblox/Levels/`.
3. Chon cac FBX trong Unity. De `Scale Factor = 1` truoc. Importer se tu fit
   bounds cua model theo `size`, nen van xu ly duoc chenh lech don vi va model
   `RMP_005` co chieu cao mesh khac chieu cao o luoi.
4. Tao mot material dung shader cua game. Voi URP, nen dung
   `Universal Render Pipeline/Lit`. Mau piece duoc gan qua `_BaseColor`; Built-in
   Standard se dung `_Color`.

Khong can dat FBX vao `Resources`. Cac model duoc tham chieu truc tiep trong
Inspector nen Unity se dua chung vao build.

## 3. Tao importer C#

Tao file `Assets/Racblox/Scripts/RacbloxLevelImporter.cs`:

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public sealed class RacbloxLevelData
{
    public RacbloxPieceData[] pieces;
}

[Serializable]
public sealed class RacbloxPieceData
{
    public string id;
    public int[] pos;
    public int rot;
    public int color;
}

[Serializable]
public sealed class RacbloxPieceDefinition
{
    public string id;
    public GameObject prefab;
    public Vector3 size = Vector3.one;
    public Vector3 pivot = Vector3.one * 0.5f;
}

public sealed class RacbloxLevelImporter : MonoBehaviour
{
    [Header("Input")]
    [SerializeField] private TextAsset levelJson;
    [SerializeField] private List<RacbloxPieceDefinition> definitions =
        new List<RacbloxPieceDefinition>();

    [Header("Output")]
    [SerializeField] private Transform generatedRoot;
    [SerializeField, Min(0.001f)] private float cellSize = 1f;
    [SerializeField] private Material overrideMaterial;
    [SerializeField] private bool addMeshColliders;

    private static readonly string[] PaletteHex =
    {
        "BE4A2F", "D77643", "EAD4AA", "E4A672",
        "B86F50", "733E39", "3E2731", "A22633",
        "E43B44", "F77622", "FEAE34", "FEE761",
        "63C74D", "3E8948", "265C42", "193C3E",
        "124E89", "0099DB", "2CE8F5", "FFFFFF",
        "C0CBDC", "8B9BB4", "5A6988", "3A4466",
        "262B44", "181425", "FF0044", "68386C",
        "B55088", "F6757A", "E8B796", "C28569"
    };

    [ContextMenu("Build Level")]
    public void BuildLevel()
    {
        if (levelJson == null)
        {
            Debug.LogError("Racblox: Missing level JSON.", this);
            return;
        }

        RacbloxLevelData level = JsonUtility.FromJson<RacbloxLevelData>(levelJson.text);
        if (level == null || level.pieces == null)
        {
            Debug.LogError("Racblox: JSON must contain a pieces array.", this);
            return;
        }

        Dictionary<string, RacbloxPieceDefinition> byId =
            new Dictionary<string, RacbloxPieceDefinition>(StringComparer.OrdinalIgnoreCase);

        foreach (RacbloxPieceDefinition definition in definitions)
        {
            if (definition != null && !string.IsNullOrWhiteSpace(definition.id))
                byId[definition.id] = definition;
        }

        Transform output = EnsureGeneratedRoot();
        ClearChildren(output);

        int created = 0;
        foreach (RacbloxPieceData piece in level.pieces)
        {
            if (piece == null || piece.pos == null || piece.pos.Length != 3)
            {
                Debug.LogWarning("Racblox: Skipped piece with invalid pos.", this);
                continue;
            }

            RacbloxPieceDefinition definition;
            if (!byId.TryGetValue(piece.id, out definition) || definition.prefab == null)
            {
                Debug.LogWarning("Racblox: Missing definition/prefab for " + piece.id, this);
                continue;
            }

            CreatePiece(output, piece, definition, created);
            created++;
        }

        Debug.Log("Racblox: Created " + created + " pieces.", this);
    }

    [ContextMenu("Clear Level")]
    public void ClearLevel()
    {
        if (generatedRoot != null)
            ClearChildren(generatedRoot);
    }

    private void CreatePiece(
        Transform output,
        RacbloxPieceData piece,
        RacbloxPieceDefinition definition,
        int index)
    {
        GameObject pivotObject = new GameObject(index + "_" + piece.id);
        Transform pivotTransform = pivotObject.transform;
        pivotTransform.SetParent(output, false);

        GameObject visual = Instantiate(definition.prefab, pivotTransform);
        visual.name = definition.prefab.name;
        visual.transform.localPosition = Vector3.zero;
        visual.transform.localRotation = Quaternion.identity;
        visual.transform.localScale = Vector3.one;

        FitVisualToGrid(visual.transform, pivotTransform, definition);

        pivotTransform.localPosition = new Vector3(
            piece.pos[0] + definition.pivot.x,
            piece.pos[1],
            piece.pos[2] + definition.pivot.z
        ) * cellSize;
        pivotTransform.localRotation = Quaternion.Euler(0f, piece.rot, 0f);

        ApplyColor(visual, piece.color);
        if (addMeshColliders)
            AddColliders(visual);
    }

    private void FitVisualToGrid(
        Transform visual,
        Transform pivotSpace,
        RacbloxPieceDefinition definition)
    {
        Bounds bounds;
        if (!TryGetMeshBounds(visual.gameObject, pivotSpace, out bounds))
        {
            Debug.LogWarning("Racblox: No mesh found on " + definition.id, visual);
            return;
        }

        Vector3 targetSize = definition.size * cellSize;
        Vector3 scale = new Vector3(
            SafeRatio(targetSize.x, bounds.size.x),
            SafeRatio(targetSize.y, bounds.size.y),
            SafeRatio(targetSize.z, bounds.size.z)
        );
        visual.localScale = Vector3.Scale(visual.localScale, scale);

        if (!TryGetMeshBounds(visual.gameObject, pivotSpace, out bounds))
            return;

        Vector3 center = definition.size * 0.5f;
        Vector3 targetCenter = new Vector3(
            center.x - definition.pivot.x,
            center.y,
            center.z - definition.pivot.z
        ) * cellSize;
        visual.localPosition += targetCenter - bounds.center;
    }

    private static float SafeRatio(float target, float current)
    {
        return Mathf.Abs(current) < 0.00001f ? 1f : target / current;
    }

    private static bool TryGetMeshBounds(
        GameObject target,
        Transform space,
        out Bounds result)
    {
        MeshFilter[] filters = target.GetComponentsInChildren<MeshFilter>(true);
        result = default(Bounds);
        bool hasPoint = false;

        foreach (MeshFilter filter in filters)
        {
            if (filter.sharedMesh == null)
                continue;

            Bounds localBounds = filter.sharedMesh.bounds;
            Matrix4x4 toSpace = space.worldToLocalMatrix * filter.transform.localToWorldMatrix;

            for (int x = -1; x <= 1; x += 2)
            for (int y = -1; y <= 1; y += 2)
            for (int z = -1; z <= 1; z += 2)
            {
                Vector3 corner = localBounds.center + Vector3.Scale(
                    localBounds.extents,
                    new Vector3(x, y, z)
                );
                Vector3 point = toSpace.MultiplyPoint3x4(corner);

                if (!hasPoint)
                {
                    result = new Bounds(point, Vector3.zero);
                    hasPoint = true;
                }
                else
                {
                    result.Encapsulate(point);
                }
            }
        }

        return hasPoint;
    }

    private void ApplyColor(GameObject target, int colorId)
    {
        if (colorId < 0 || colorId >= PaletteHex.Length)
        {
            Debug.LogWarning("Racblox: Invalid color ID " + colorId, target);
            return;
        }

        Color color;
        if (!ColorUtility.TryParseHtmlString("#" + PaletteHex[colorId], out color))
            return;

        foreach (Renderer renderer in target.GetComponentsInChildren<Renderer>(true))
        {
            if (overrideMaterial != null)
                renderer.sharedMaterial = overrideMaterial;

            Material material = renderer.sharedMaterial;
            if (material == null)
                continue;

            MaterialPropertyBlock block = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(block);

            if (material.HasProperty("_BaseColor"))
                block.SetColor("_BaseColor", color);
            if (material.HasProperty("_Color"))
                block.SetColor("_Color", color);

            renderer.SetPropertyBlock(block);
        }
    }

    private static void AddColliders(GameObject target)
    {
        foreach (MeshFilter filter in target.GetComponentsInChildren<MeshFilter>(true))
        {
            if (filter.sharedMesh == null || filter.GetComponent<Collider>() != null)
                continue;

            MeshCollider collider = filter.gameObject.AddComponent<MeshCollider>();
            collider.sharedMesh = filter.sharedMesh;
        }
    }

    private Transform EnsureGeneratedRoot()
    {
        if (generatedRoot != null)
            return generatedRoot;

        GameObject root = new GameObject("Generated Racblox Level");
        root.transform.SetParent(transform, false);
        generatedRoot = root.transform;
        return generatedRoot;
    }

    private static void ClearChildren(Transform root)
    {
        for (int i = root.childCount - 1; i >= 0; i--)
        {
            GameObject child = root.GetChild(i).gameObject;
            if (Application.isPlaying)
                Destroy(child);
            else
                DestroyImmediate(child);
        }
    }
}
```

## 4. Cau hinh trong Inspector

1. Tao mot empty GameObject ten `Racblox Level`.
2. Gan component `RacbloxLevelImporter`.
3. Keo file JSON export vao `Level Json`.
4. Keo material URP/Built-in vao `Override Material` neu muon dung mau palette.
5. Trong `Definitions`, tao entry cho tung piece can dung:
   - `Id`: vi du `blk_001`.
   - `Prefab`: keo `BLK_001.fbx` vao.
   - `Size`: copy `size` tu `library/blk_001/piece.json`.
   - `Pivot`: copy `pivot` tu cung file.
6. Giu transform cua `Racblox Level` o Position `(0,0,0)`, Rotation `(0,0,0)`,
   Scale `(1,1,1)` trong lan import dau tien.
7. Mo menu ba cham cua component va chon **Build Level**.

Importer tu dong:

- fit bounds FBX theo kich thuoc o luoi;
- xoay dung quanh pivot rieng cua tung piece;
- gan 32 mau Racblox bang `MaterialPropertyBlock`, khong clone material cho moi
  object;
- tao `MeshCollider` neu bat `Add Mesh Colliders`.

## 5. Kiem tra nhanh

Dung mot map nho truoc khi import map lon:

1. Dat mot `blk_001` tai `[0,0,0]`: bounds phai la 1 x 1 x 1 Unity unit khi
   `Cell Size = 1`.
2. Dat `blk_003` voi rotation 0 va 90: model phai doi tu chieu Z sang chieu X.
3. Dat `rmp_002` voi rotation 0, 90, 180 va 270: canh neo phai giong Racblox.
4. Thu color 0, 19 va 25: lan luot phai ra nau-do, trang va mau rat toi.
5. Bat collider visualization de dam bao collider di theo model da fit.

## 6. Loi thuong gap

- **Model lon/nho sai 100 lan:** giu `Cell Size = 1`; importer se fit bounds. Neu
  prefab co script hoac object phu, nen tao prefab chi chua mesh Racblox.
- **Mat piece:** Console se bao `Missing definition/prefab`. Them dung ID viet
  trong JSON; importer khong phan biet hoa-thuong.
- **Mau khong thay doi:** shader can property `_BaseColor` hoac `_Color`. Gan
  mot URP Lit material vao `Override Material` la cach nhanh nhat.
- **Xoay sai diem neo:** khong tu thay `pivot` bang nua `size`. Mot so ramp va
  block dai co pivot co chu dich khac tam.
- **JSON khong doc duoc:** dung file **Export Game JSON**, khong doi object goc
  `{"pieces": [...]}` thanh array don.
- **Can chinh ca level:** di chuyen/rotate GameObject `Racblox Level` sau khi
  build; khong sua tung piece neu con muon rebuild tu JSON.

## 7. Build game

FBX duoc tham chieu trong danh sach `Definitions`, do do Unity se giu chung khi
build player. File JSON la `TextAsset` cung duoc tham chieu boi component. Khong
can copy JSON hoac FBX canh file `.exe` cua game Unity.

Neu level can tai tu server hoac cap nhat ma khong build lai game, thay
`TextAsset levelJson` bang JSON doc tu `StreamingAssets`, Addressables hoac API;
phan mapping piece, pivot va palette giu nguyen.
