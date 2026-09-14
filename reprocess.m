function reprocess(imageListCsv, roiName, method)
% reprocess - Analyze image pairs for motion statistics using SIFT and enhancement filters
%
% Parameters:
%   imageListCsv (string): Path to CSV file containing image names in first column
%   roiName (string): ROI name like 'ROI1', 'ROI2', 'ROI3', or 'ROI4'
%   method (string): Filter method to use ('canny', 'adapthisteq', 'nofilter')

% Input validation
if nargin < 3
    error('All parameters (imageListCsv, roiName, method) are required.');
end

% Validate method input
validMethods = {'canny','adapthisteq','nofilter'};
if ~ismember(lower(method), validMethods)
    error('Invalid method. Choose from: canny, adapthisteq, nofilter');
end

% Start the timer
tic;

% Read image names from CSV
imageNamesTable = readtable(imageListCsv);
imageNamesRaw = string(imageNamesTable{:,1});
imageNames = extractBefore(imageNamesRaw, ',');
numImages = length(imageNames)

% Generate all combinations of image pairs
pairList = nchoosek(1:numImages, 2);
pairTable = table(imageNames(pairList(:,1)), imageNames(pairList(:,2)), ...
    'VariableNames', {'ImageA', 'ImageB'});

% Extract folder tag (e.g., Grp1)
[~, folderTag, ~] = fileparts(imageListCsv);

% Output file names
outputCsvFile = sprintf('motion_statistics_%s_%s_%s.csv', roiName, folderTag, method);
folder_result = sprintf('result_%s_%s_%s', roiName, folderTag, method);
outputmatFile = sprintf('motion_stat_%s_%s_%s.mat', roiName, folderTag, method);

% Base image path
imageBasePath = "/media/nasdata_field/Terrestrial Images/Data_DD/JPG/";

% Create results folder if it doesn't exist
if ~exist(folder_result, 'dir')
    mkdir(folder_result);
end

% Remove existing CSV file to start fresh
if isfile(outputCsvFile)
    delete(outputCsvFile);
end

% ----------------------------
% ROI Definitions
% ----------------------------

stableROI.GRP1 = [681 3314 654 78];
motionROI.GRP1.ROI1 = [4515 3014 654 78];
motionROI.GRP1.ROI2 = [3969 3194 588 108];
motionROI.GRP1.ROI3 = [3165 3512 606 84];
motionROI.GRP1.ROI4 = [3009 3200 336 138];

stableROI.GRP2 = [1455 3422 414 150];
motionROI.GRP2.ROI1 = [5284 3160 493 101];
motionROI.GRP2.ROI2 = [4695 3368 642 113];
motionROI.GRP2.ROI3 = [3843 3642 778 115];
motionROI.GRP2.ROI4 = [3922 3297 403 151];

stableROI.GRP3 = [1347 3290 416 178];
motionROI.GRP3.ROI1 = [5289 3065 499 124];
motionROI.GRP3.ROI2 = [4540 3338 576 136];
motionROI.GRP3.ROI3 = [3547 3540 570 130];
motionROI.GRP3.ROI4 = [3755 3195 338 172];

% Determine group key from filename (case-insensitive)
folderKey = upper(regexprep(folderTag, '\.csv$', ''));

if isfield(stableROI, folderKey) && isfield(motionROI.(folderKey), roiName)
    stablePos = stableROI.(folderKey);
    motionPos = motionROI.(folderKey).(roiName);
else
    error('Invalid image group or ROI name provided.');
end


% Count total valid pairs
totalPairs = height(pairTable);

% Start parallel pool
pool = gcp('nocreate');
if isempty(pool)
    parpool(8); % Adjust number of cores if needed
end

% Initialize progress tracking
progressQueue = parallel.pool.DataQueue;
afterEach(progressQueue, @(data) fprintf('Processed %d/%d pairs\n', data, totalPairs));

% Preallocate result container
parResults = cell(totalPairs, 1);

% Parallel loop for image pairs
parfor pairIdx = 1:totalPairs
    try
        % Get image names
        nameA = strtrim(pairTable{pairIdx, 1}{1});
        nameB = strtrim(pairTable{pairIdx, 2}{1});

        % Full image paths
        imageAPath = fullfile(imageBasePath, nameA);
        imageBPath = fullfile(imageBasePath, nameB);

        % Read images and metadata
        [imageA, dateA] = readImageWithMetadata(imageAPath);
        [imageB, dateB] = readImageWithMetadata(imageBPath);

        % Convert to grayscale
        grayA = rgb2gray(imageA);
        grayB = rgb2gray(imageB);

        % Process stable region
        stableData = processAndSaveStatistics(grayA, grayB, stablePos, ...
            'stable_region', dateA, dateB, [], folder_result, method);

        % Process motion region
        motionData = processAndSaveStatistics(grayA, grayB, motionPos, ...
            'motion_region', dateA, dateB, [], folder_result, method);

        % Store results
        parResults{pairIdx} = {stableData; motionData};

        send(progressQueue, pairIdx);

    catch ME
        warning('Error processing pair %d: %s', pairIdx, getReport(ME));
    end
end

% Flatten results and save
csvData = vertcat(parResults{:});
save(outputmatFile, 'csvData');

% Save to CSV
Data_filtering(outputCsvFile, csvData);

% Elapsed time
elapsedTime = toc;

% Display summary
fprintf('Processing complete.\nResults saved to: %s\n', outputCsvFile);
fprintf('Elapsed time: %.2f seconds (%.2f minutes)\n', elapsedTime, elapsedTime/60);
end


function enhancedImage = enhanceImage(img, method, roiPos)
Crop = imcrop(img, roiPos);
switch lower(method)
    case 'canny'
        [~, threshold] = edge(Crop, 'canny');
        Crop_edge = edge(Crop, 'canny', threshold * 0.5);
        enhancedImage = double(Crop_edge) .* double(Crop);

    case 'adapthisteq'
        enhancedImage =  adapthisteq(Crop);

    case 'nofilter'
        enhancedImage =  Crop;
    otherwise
        error('Unsupported enhancement method');
end
end

function header = assigningHeaderToCsv(~)
% Write the header row to the CSV file
header = {'Region Type', 'Image Date A', 'Image Date B', 'Days Between', ...
    'Number of Vectors', 'Mean Magnitude (95%)', 'Mean Magnitude', ...
    'Median Magnitude', 'Std Dev Magnitude', 'NMAD Magnitude', ...
    'Mean Direction (95%)', 'Mean Direction', 'Median Direction', ...
    'Std Dev Direction', 'NMAD Direction', ...
    'Mean Motion X', 'Median Motion X', 'Std Dev Motion X', 'NMAD Motion X', ...
    'Mean Motion Y', 'Median Motion Y', 'Std Dev Motion Y', 'NMAD Motion Y', ...
    'Mean Magnitude per Week','Region Type', 'Image Date A', 'Image Date B', 'Days Between', ...
    'Number of Vectors', 'Mean Magnitude (95%)', 'Mean Magnitude', ...
    'Median Magnitude', 'Std Dev Magnitude', 'NMAD Magnitude', ...
    'Mean Direction (95%)', 'Mean Direction', 'Median Direction', ...
    'Std Dev Direction', 'NMAD Direction', ...
    'Mean Motion X', 'Median Motion X', 'Std Dev Motion X', 'NMAD Motion X', ...
    'Mean Motion Y', 'Median Motion Y', 'Std Dev Motion Y', 'NMAD Motion Y', ...
    'Mean Magnitude per Week'};

% Step 1: Check if the header contains 48 columns
if numel(header) ~= 48
    error('Expected 48 column names, but got %d. Please check the header.', numel(header));
end

% Step 2: Add suffixes
header(1:24) = strcat(header(1:24), '_motion');  % Add "_stable" suffix to the first 24 headers
header(25:48) = strcat(header(25:48), '_stable'); % Add "_motion" suffix to the next 24 headers
end

function pos = selectROI(image, titleText)
% Function to select ROI using a rectangle tool
figure, imshow(image), title(titleText);
roi = drawrectangle;
wait(roi);
pos = round(roi.Position); % [x, y, width, height]
close;
end

function [image, imageDate] = readImageWithMetadata(imagePath)
% Read the image
image = imread(imagePath);

% Extract metadata (assuming Exif metadata contains a date field)
info = imfinfo(imagePath);
if isfield(info, 'DateTime')
    imageDate = datetime(info.DateTime, 'InputFormat', 'yyyy:MM:dd HH:mm:ss');
else
    warning('No metadata date found for: %s. Using today''s date.', imagePath);
    imageDate = datetime('now'); % Default to current date
end
end


function csvData = processAndSaveStatistics(grayA, grayB, regionPos, regionType, dateA, dateB, csvData,folder_result,method)

% Create result folder
resultFolder = fullfile(folder_result, sprintf('%s_%s_%d_days', ...
    datestr(dateA, 'yyyymmdd'), datestr(dateB, 'yyyymmdd'), ...
    round(days(dateB - dateA))));
if ~exist(resultFolder, 'dir')
    mkdir(resultFolder);
end
% Analyze motion in the region
[movementMagnitude, movementDirection] = analyzeRegion(grayA, grayB, regionPos, resultFolder, regionType, dateA, dateB, method);

% Skip if no motion data
if isempty(movementMagnitude)
    warning('No motion vectors detected for region: %s', regionType);
    return;
end

% Append statistics to the CSV data
csvData = appendStatistics(csvData, regionType, movementMagnitude, ...
    movementDirection, dateA, dateB);
saveStatistics_pair(resultFolder, regionType, movementMagnitude, movementDirection, dateA, dateB);
plotHistograms(movementMagnitude, movementDirection, regionType, resultFolder);
end

function [movementMagnitude, movementDirection] = analyzeRegion(imageA, imageB, roiPos, resultFolder, regionType, dateA, dateB, method)
% Crop the regions
% Apply image enhancement based on method
regionCropA = enhanceImage(imageA, method, roiPos);
regionCropB = enhanceImage(imageB, method, roiPos);

% Save cropped regions
imwrite(regionCropA, fullfile(resultFolder, [regionType, '_A.jpg']));
imwrite(regionCropB, fullfile(resultFolder, [regionType, '_B.jpg']));
% Analyze motion
%disp(['Analyzing ', regionType, ' region...']);
[movementMagnitude, movementDirection] = analyzeFeatureMotion(regionCropA, regionCropB, resultFolder, regionType, dateA, dateB);

end

function csvData = appendStatistics(csvData, regionType, movementMagnitude,movementDirection, dateA, dateB)
% Calculate X and Y motion components
motionX = movementMagnitude .* cosd(movementDirection); % Use degrees
motionY = movementMagnitude .* sind(movementDirection); % Use degrees

% Calculate statistics
stats = calculateStatistics(movementMagnitude, movementDirection, motionX, motionY);
daysBetween = round(days(dateB - dateA));
meanMagnitudePerWeek = mean(movementMagnitude, 'omitnan') / daysBetween;

% Append to the data array
newRow = {regionType, dateA, dateB, daysBetween, ...
    numel(movementMagnitude), stats.MeanMagnitude95, ...
    stats.MeanMagnitude, stats.MedianMagnitude, stats.StdMagnitude, ...
    stats.NMADMagnitude, stats.MeanDirection95, stats.MeanDirection, ...
    stats.MedianDirection, stats.StdDirection, stats.NMADDirection, ...
    stats.MeanMotionX, stats.MedianMotionX, stats.StdMotionX, stats.NMADX, ...
    stats.MeanMotionY, stats.MedianMotionY, stats.StdMotionY, stats.NMADY, ...
    meanMagnitudePerWeek};

csvData = [csvData; newRow];
end

function [movementMagnitude, movementDirection] = analyzeFeatureMotion(imageA, imageB, resultFolder, regionType, dateA, dateB)
% Parameters for SIFT feature detection
contrastThreshold = 0.01; % Lower value detects more features
edgeThreshold = 10;       % Higher value allows more edge-like features
numOctaves = 4;           % Number of octaves (scale levels)
sigma = 1.6;              % Sigma for Gaussian filter
BlockSize = 11;
FeatureSize =  64;
NumPyramidLevels = 3;
MaxBidirectionalError =2;
BlockSize = [31,31];
MaxIterations = 30;
trackedPoints = 'affine';
MaxNumTrials =  5000;
Confidence =  99;
MaxDistance = 2000;

% Detect features with customizable parameters
pointsA = detectSIFTFeatures(imageA);%,'ContrastThreshold', contrastThreshold,'EdgeThreshold', edgeThreshold,'NumLayersInOctave', numOctaves,'Sigma', sigma);

% Extract features
[featuresA, validPointsA] = extractFeatures(imageA, pointsA);

% Initialize point tracker
tracker = vision.PointTracker('MaxBidirectionalError', 2);
initialize(tracker, validPointsA.Location, imageA);

% Track points in the second image
[trackedPoints, validity] = tracker(imageB);
release(tracker);

% Filter valid points
trackedPoints = trackedPoints(validity, :);
initialPoints = validPointsA.Location(validity, :);

% Step 1: RANSAC for initial inlier estimation
[~, inlierIdx] = estgeotform2d(initialPoints, trackedPoints, 'affine', ...
    'MaxNumTrials', 5000, 'Confidence', 99, 'MaxDistance', 2000);

% Filter inliers from RANSAC
inlierInitialPoints = initialPoints(inlierIdx, :);
inlierTrackedPoints = trackedPoints(inlierIdx, :);

% Step 2: Calculate motion vectors and directions
inlierMotionVectors = inlierTrackedPoints - inlierInitialPoints;
inlierMovementMagnitude = vecnorm(inlierMotionVectors, 2, 2);
inlierMovementDirection = atan2d(inlierMotionVectors(:, 2), inlierMotionVectors(:, 1));

% Step 3: Filter inliers based on motion direction
[finalInliers, refinedModelDirection] = filterByDirection(inlierMovementDirection, 30); % 10-degree threshold
finalInitialPoints = inlierInitialPoints(finalInliers, :);
finalTrackedPoints = inlierTrackedPoints(finalInliers, :);
finalMotionVectors = inlierMotionVectors(finalInliers, :);
movementMagnitude = inlierMovementMagnitude(finalInliers);
movementDirection = inlierMovementDirection(finalInliers);
plotMotionVectors(imageB, finalInitialPoints, finalMotionVectors, regionType, resultFolder);
end

function [finalInliers, modelDirection] = filterByDirection(directions, threshold)
% Custom filtering of inliers based on direction similarity
% directions: Array of movement directions (degrees)
% threshold: Allowed deviation from the model direction (degrees)
% Use the median direction as the model (robust against outliers)
modelDirection = median(directions);
% Calculate absolute differences from the model direction
directionDiff = abs(directions - modelDirection);
% Wrap around 360 degrees
directionDiff(directionDiff > 180) = 360 - directionDiff(directionDiff > 180);
% Identify inliers within the threshold
finalInliers = directionDiff <= threshold;
end

function saveStatistics_pair(resultFolder, regionType, movementMagnitude, movementDirection, dateA, dateB)
% Define the output file name
outputFileName = fullfile(resultFolder, 'glacier_motion_stats.txt');
% Open the file for appending
fileID = fopen(outputFileName, 'a');
if fileID == -1
    error('Failed to open file: %s. Check file path or permissions.', outputFileName);
end

% Check if motion data is empty
if isempty(movementMagnitude) || isempty(movementDirection)
    %disp(['Warning: No motion vectors detected for ', regionType]);
    return; % Skip saving statistics if no motion data
end

% Calculate X and Y motion components
motionX = movementMagnitude .* cosd(movementDirection); % Use degrees
motionY = movementMagnitude .* sind(movementDirection); % Use degrees

% Calculate statistics
stats = calculateStatistics(movementMagnitude, movementDirection, motionX, motionY);
daysBetween = round(days(dateB - dateA));
weeksBetween = daysBetween / 7;
meanMagnitudePerWeek = mean(movementMagnitude, 'omitnan') / weeksBetween;

% Write statistics to the file
fprintf(fileID, '--- Analysis for %s ---\n', regionType);
fprintf(fileID, 'Image Date A: %s\n', datestr(dateA, 'dd-mmm-yyyy HH:MM:SS'));
fprintf(fileID, 'Image Date B: %s\n', datestr(dateB, 'dd-mmm-yyyy HH:MM:SS'));
fprintf(fileID, 'Day Gap Between Images: %d days\n', daysBetween);
fprintf(fileID, 'Number of Vectors: %d\n', numel(movementMagnitude));

fprintf(fileID, 'Magnitude Statistics:\n');
fprintf(fileID, '  Mean (95%%): %.4f\n', stats.MeanMagnitude95);
fprintf(fileID, '  Mean: %.4f\n', stats.MeanMagnitude);
fprintf(fileID, '  Median: %.4f\n', stats.MedianMagnitude);
fprintf(fileID, '  Std Dev: %.4f\n', stats.StdMagnitude);
fprintf(fileID, '  NMAD: %.4f\n\n', stats.NMADMagnitude);

fprintf(fileID, 'Direction Statistics:\n');
fprintf(fileID, '  Mean (95%%): %.4f\n', stats.MeanDirection95);
fprintf(fileID, '  Mean: %.4f\n', stats.MeanDirection);
fprintf(fileID, '  Median: %.4f\n', stats.MedianDirection);
fprintf(fileID, '  Std Dev: %.4f\n', stats.StdDirection);
fprintf(fileID, '  NMAD: %.4f\n\n', stats.NMADDirection);

fprintf(fileID, 'X Motion Statistics:\n');
fprintf(fileID, '  Mean: %.4f\n', stats.MeanMotionX);
fprintf(fileID, '  Median: %.4f\n', stats.MedianMotionX);
fprintf(fileID, '  Std Dev: %.4f\n', stats.StdMotionX);
fprintf(fileID, '  NMAD: %.4f\n\n', stats.NMADX);

fprintf(fileID, 'Y Motion Statistics:\n');
fprintf(fileID, '  Mean: %.4f\n', stats.MeanMotionY);
fprintf(fileID, '  Median: %.4f\n', stats.MedianMotionY);
fprintf(fileID, '  Std Dev: %.4f\n', stats.StdMotionY);
fprintf(fileID, '  NMAD: %.4f\n\n', stats.NMADY);

fprintf(fileID, 'Mean Magnitude per Week: %.4f\n\n', meanMagnitudePerWeek);
fclose(fileID);
%disp(['Statistics saved to ', outputFileName]);
end

function stats = calculateStatistics(magnitude, direction, motionX, motionY)
% Calculate statistics for magnitude and direction
stats.MeanMagnitude = mean(magnitude, 'omitnan');
stats.MeanMagnitude95 = mean(magnitude(magnitude < prctile(magnitude, 95)), 'omitnan');
stats.MedianMagnitude = median(magnitude, 'omitnan');
stats.StdMagnitude = std(magnitude, 'omitnan');
stats.NMADMagnitude = 1.4826 * mad(magnitude, 1);

stats.MeanDirection = mean(direction, 'omitnan');
stats.MeanDirection95 = mean(direction(direction < prctile(direction, 95)), 'omitnan');
stats.MedianDirection = median(direction, 'omitnan');
stats.StdDirection = std(direction, 'omitnan');
stats.NMADDirection = 1.4826 * mad(direction, 1);

% Calculate statistics for X motion
stats.MeanMotionX = mean(motionX, 'omitnan');
stats.MedianMotionX = median(motionX, 'omitnan');
stats.StdMotionX = std(motionX, 'omitnan');
stats.NMADX = 1.4826 * mad(motionX, 1);

% Calculate statistics for Y motion
stats.MeanMotionY = mean(motionY, 'omitnan');
stats.MedianMotionY = median(motionY, 'omitnan');
stats.StdMotionY = std(motionY, 'omitnan');
stats.NMADY = 1.4826 * mad(motionY, 1);
end

function plotMotionVectors(image, initialPoints, motionVectors, regionType, resultFolder)
% Plot motion vectors
figure;
imshow(image);
hold on;
quiver(initialPoints(:, 1), initialPoints(:, 2), motionVectors(:, 1), motionVectors(:, 2), 0, 'r', 'LineWidth', 1);
title(['Feature Movement - ', regionType], 'Interpreter', 'none');
hold off;

% Save the plot in high resolution
saveFilePath = fullfile(resultFolder, [regionType, '_motion_vectors.png']);
drawnow; % Ensure figure is rendered before saving
print(gcf, saveFilePath, '-dpng', '-r600'); % Save at 300 DPI
%disp(['Motion vectors plot saved to ', saveFilePath]);
close(gcf); % Close figure after saving
end

function plotHistograms(magnitude, direction, regionType, resultFolder)
% Plot histograms of motion magnitude and direction
figure;
subplot(2, 1, 1);
histogram(magnitude, 20);
title(['Histogram of Motion Magnitude - ', regionType], 'Interpreter', 'none');
xlabel('Motion Magnitude (pixels)');
ylabel('Frequency');

subplot(2, 1, 2);
histogram(direction, 20);
title(['Histogram of Motion Direction - ', regionType], 'Interpreter', 'none');
xlabel('Direction (degrees)');
ylabel('Frequency');

% Save the plot in high resolution
saveFilePath = fullfile(resultFolder, [regionType, '_histograms.png']);
drawnow; % Ensure figure is rendered before saving
print(gcf, saveFilePath,'-dpng', '-r300');
%disp(['Histograms saved to ', saveFilePath]);
close(gcf); % Close figure after saving
end
function Data_filtering(outputCsvFile, csvData)
% Step 1: Remove empty cells
csvData = csvData(~cellfun('isempty', csvData)); % Remove empty cells

% Step 2: Find unique region types from the first column
regionTypes = unique(cellfun(@(x) x{1}, csvData, 'UniformOutput', false)); % Extract unique region types

% Initialize the region containers
motionRegion = {}; % Initialize for "Motion Region"
stableRegion = {}; % Initialize for "Stable Region"

% Step 3: Sort rows into motionRegion and stableRegion based on unique region types
for i = 1:length(csvData)
    row = csvData{i}; % Extract the current row
    if iscell(row) && numel(row) == 24 % Ensure the row is a 1x16 cell array
        regionType = row{1}; % Extract 'Region Type' (column 1)

        % Check if regionType matches any unique value and append accordingly
        if strcmp(regionType, regionTypes{1}) % Dynamically compare with first unique value
            motionRegion = [motionRegion; {row}]; % Append the full row as a cell array
        elseif strcmp(regionType, regionTypes{2}) % Compare with second unique value
            stableRegion = [stableRegion; {row}]; % Append the full row as a cell array
        end
    end
end

% Step 4: Extract dates (row{2} and row{3}) for comparison
motionDates = cellfun(@(x) x([2, 3]), motionRegion, 'UniformOutput', false);
stableDates = cellfun(@(x) x([2, 3]), stableRegion, 'UniformOutput', false);

% Step 5: Convert dates to tables for comparison
motionDatesTable = cell2table(vertcat(motionDates{:}), 'VariableNames', {'ImageDateA', 'ImageDateB'});
stableDatesTable = cell2table(vertcat(stableDates{:}), 'VariableNames', {'ImageDateA', 'ImageDateB'});

% Step 6: Find matching rows
[commonDates, motionIdx, stableIdx] = intersect(motionDatesTable, stableDatesTable, 'rows');

% Step 7: Filter rows based on matching indices
filteredMotionRegion = motionRegion(motionIdx);
filteredStableRegion = stableRegion(stableIdx);

% Step 8: Concatenate matching rows horizontally
finalData = cellfun(@(x, y) [x, y], filteredMotionRegion, filteredStableRegion, 'UniformOutput', false);
finalData = vertcat(finalData{:}); % Combine into a single cell array

% Step 9: Convert to table for CSV export
finalDataTable = cell2table(finalData);
header = assigningHeaderToCsv(outputCsvFile);
finalDataTable.Properties.VariableNames = header; % Set the header as column names

end

