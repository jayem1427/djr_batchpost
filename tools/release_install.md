---

## Install / upgrade

1. Download **`djr_batchpost-v{version}.zip`** below (not the "Source code" zips) and unzip it. You get a folder named `djr_batchpost`. Don't rename it: Fusion needs the folder name to match the files inside.
2. Copy that folder into Fusion's add-ins folder, replacing the old one if you're upgrading:
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - **Mac:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. Restart Fusion, or open **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S), select **djr_batchpost**, click **Run**, and tick **Run on startup**.
4. In the **Manufacture** workspace, right-click a setup and choose **Post Combined (DJR)**. The **DJR Batch Post** and **Post Combined** buttons are in the **Actions** panel.

**Upgrading from the old "Batch Post" add-in?** Stop it in Scripts and Add-Ins and untick its *Run on startup*, so you don't get duplicate buttons. Your per-document settings carry over.

> Always check new output in a G-code viewer and air-cut before running it on the machine.

Full history: [CHANGELOG.md](https://github.com/jayem1427/djr_batchpost/blob/main/CHANGELOG.md)
