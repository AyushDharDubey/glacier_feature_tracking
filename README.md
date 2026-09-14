# Glacier Motion Tracking Manual

## 1. Overview
This MATLAB pipeline estimates glacier velocity and movement vectors between sequential pairs of images. It performs edge detection (Canny), SIFT feature extraction, and feature tracking, filtering vectors using RANSAC and direction consistency. Results and plots are automatically generated for both a user-defined Stable Region and Motion Region.

---

## 2. Prerequisites & Dependencies

### A. Software Requirements
- **MATLAB** (R2020a or newer recommended).

### B. Input Data Requirements
- A directory containing at least 2 JPEG images (`.JPG` or `.jpg`).
- Images should contain EXIF metadata with date-time stamps (`DateTime` property). If missing, current system time will be used as a fallback.

---

## 3. Folder Structure Setup
Place your MATLAB script inside your working directory. Organize your dataset folder as shown below:

```text
Your_Project_Directory/
│
├── main.m                      <-- Your MATLAB script
└── 2023_Winter/                <-- Input folder with image pairs
    ├── IMG_0001.JPG
    ├── IMG_0002.JPG
    └── IMG_0003.JPG
```

---

## 4. Configuration Steps (Inside `main.m`)
Before running the code, adjust the primary configuration settings at the top of the `main()` function:

### A. Set Image and Output Folder Paths
```matlab
imageFolder = '2023_Winter';                                  % Directory with input images
outputCsvFile = 'glacier_motion_statistics_winter_canny.csv';  % Final output CSV path
folder_result = 'result_2023_winter_canny1';                   % Directory where plots/txt stats will be saved
outputmatFile = 'glacier_motion_statistics_winter_canny.mat';  % Workspace backup file
```

### B. Define Regions of Interest (ROIs)
An ROI vector is formatted as: `[X_min, Y_min, Width, Height]`.

- **Option 1: Hardcoded Coordinates (Default)**
  ```matlab
  stablePos = [];  % [X, Y, Width, Height] for stationary reference ground
  motionPos = [];  % [X, Y, Width, Height] for moving glacier region
  ```

- **Option 2: Interactive ROI Selection (Optional)**  
  Uncomment these lines if you want to select regions visually on the first image before running parallel execution:
  ```matlab
  stablePos = selectROI(firstImage, 'Draw ROI for the stable region');
  motionPos = selectROI(firstImage, 'Draw ROI for the motion region');
  ```

---

## 5. How to Run the Script
1. Launch MATLAB and set your working directory to the folder containing your script.
2. Open `main.m` in the MATLAB Editor.
3. Execute the script via:
   - Click the green Run button (▶) in the MATLAB Editor tab.

---

## 6. Pipeline Execution Steps
1. Scan folder & load images
2. Compute all combination pairs: `nchoosek(N, 2)`
3. Initialize parallel processing pool (`parpool`)
4. For each image pair (Parallel Processing via `parfor`):
   - Crop Stable & Motion ROIs
   - Apply Canny edge detection overlay
   - Extract SIFT features & track points (`PointTracker`)
   - Filter outliers with RANSAC & Direction Deviation
   - Generate statistics, vectors, and histogram plots
5. Merge, filter, & export consolidated data to CSV & `.mat`
6. For Metric conversion refer [https://toolstud.io/photo/dof.php](https://toolstud.io/photo/dof.php)

---

## 7. Generated Outputs & Results
After execution finishes, the following files and directories will be created:

### A. CSV Output File (`*.csv`)
Contains 48 consolidated statistical columns detailing displacement, vectors, mean/median values, standard deviations, and NMAD metrics for matched image pairs (combining motion and stable regions side-by-side).

### B. MAT Backup File (`*.mat`)
Stores raw cell array results in MATLAB format for post-processing.

### C. Detailed Results Directory (`folder_result/`)

---

## 8. Troubleshooting & Common Issues

- **Not enough images to process**  
  - *Solution:* Make sure the path specified in `imageFolder` is valid and contains at least two `.JPG` images.

- **Out of Memory or High System Load**  
  - *Solution:* Reduce `numCores` in `parpool(numCores)` (e.g., set to 4 or 2).

- **No metadata date found for...**  
  - *Warning:* Appears when EXIF data lacks a time tag. The code automatically assigns the current execution date.
