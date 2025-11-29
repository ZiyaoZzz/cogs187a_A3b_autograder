# COGS 187A Autograder - Feature Summary Report

## Overview
This document summarizes the functionality of each page in the LLM-based heuristic evaluation autograder system for Assignment 3A.

---

## 1. Home Page (`/`)

**Purpose**: Landing page and system introduction

**Key Features**:
- Displays system title and description
- Explains that the system analyzes heuristic evaluation PDFs for `visitjulian.com`
- Describes the system's capability to check coverage of Nielsen's 10 heuristics and generate structured feedback
- Provides a call-to-action button to navigate to the PDF upload page
- Includes an informational section for students/TAs explaining what they can expect from the system

---

## 2. Grade PDF Page (`/upload`)

**Purpose**: Main grading interface for student submissions

**Key Features**:

### PDF Upload & Extraction
- File upload interface for PDF submissions
- Automatic extraction of all pages from uploaded PDFs
- High-quality page rendering (200 DPI) with base64 image encoding
- Displays extracted page count and file information

### Gemini AI Analysis
- **Per-Page Analysis**: Analyzes each page using Gemini 2.5 Flash model
- **Intelligent Page Classification**: Automatically skips title pages, cover pages, and section dividers; analyzes pages with substantial heuristic violation content
- **Violation Extraction**: Extracts heuristics numbers, names, descriptions, and severity ratings from student text
- **Comprehensive Scoring**: Evaluates 8 core criteria:
  - Coverage (calculated system-wide)
  - Violation Quality (20 points)
  - Screenshots & Evidence (10 points)
  - Severity Analysis (10 points)
  - Structure & Navigation (10 points)
  - Professional Quality (10 points)
  - Writing Quality (10 points)
  - Group Integration (15 points)
- **Bonus Scoring**: Optional extra credit for AI Opportunities (3 points) and Exceptional Quality (2 points)

### Real-Time Progress Tracking
- Progress indicator showing current page being analyzed
- Displays analysis status for each page (Analyzing, Analyzed, Skipped)
- Real-time updates as pages are processed

### Slide Analysis Section (Left Column)
- Displays all extracted pages with their rendered images
- Shows Gemini analysis results for each page including:
  - Page type classification
  - Feedback with heuristics and violations discussed
  - Skip reasons for non-analyzable pages
  - Compelling/Needs Improvement indicators

### Assignment Summary & Final Score (Right Column)
- **Final Score Display**: Shows total score (base + bonus) out of 100, with bonus points as extra credit (can exceed 100)
- **Score Breakdown**: Detailed scores for all 8 core criteria with comments explaining deductions
- **Bonus Scores**: Displays AI Opportunities and Exceptional Quality scores
- **Coverage Metrics**: 
  - Total heuristics covered (out of 10 required)
  - Total violations identified (out of 12 minimum required)
- **Page Statistics**: Number of pages analyzed vs. skipped

### Student Analysis Summary (Bottom Section)
- **Per-Page Breakdown**: Lists all analyzed pages with their extracted violations
- **Heuristic & Violation Details**: For each page, displays:
  - Heuristic numbers and full names
  - Heuristic descriptions from Nielsen's 10 heuristics
  - Individual violations with descriptions
  - Severity ratings for each violation
- **Feedback Preview**: Shows truncated feedback for each page

### Comparison with Julian Site Analysis
- **Optional Feature**: Checkbox to enable comparison with reference site analysis
- **Overall Summary**: Compares student submission with Julian site analysis:
  - Total heuristics covered by student vs. Julian site
  - Total violations identified
  - Matched issues between student and reference
  - Average match score percentage
- **Best Match Display**: Shows the Julian page with highest similarity to student submission
- **Heuristic Match Rate**: Calculates how well student heuristics align with reference analysis

---

## 3. Reference Site Page (`/julian`)

**Purpose**: View and explore the reference website analysis (visitjulian.com)

**Key Features**:

### Page Navigation
- **Page List**: Sidebar displaying all crawled pages from visitjulian.com
- **Page Selection**: Click to view any page's analysis
- **Page Metadata**: Shows page ID, title, and URL for each page

### View Modes
- **Device Toggle**: Switch between Desktop and Phone views
  - Desktop: Shows desktop screenshots and analysis
  - Phone: Shows mobile screenshots and analysis (if available)
- **View Mode Toggle**: Switch between Screenshot and Overlay views
  - Screenshot: Raw captured image
  - Overlay: Annotated image with heuristic issue bounding boxes and labels

### Heuristic Issue Display
- **Issue List**: Displays all heuristic violations found on the selected page
- **Issue Details**: For each issue shows:
  - Heuristic number and name
  - Severity level (Cosmetic, Minor, Major, Critical)
  - Issue title and description
  - Visual bounding box coordinates (if available)
- **Issue Filtering**: Global toggle to hide issues possibly affected by external widgets/third-party embeds
- **Filtered Scoring**: Recalculates issue count and overall score when filtering is enabled

### Third-Party Embed Warnings
- **Warning Display**: Yellow warning box when page contains third-party embeds (iframes, embeds, video tags)
- **Embed List**: Shows shortened URLs (80 characters max) of detected third-party services
- **Issue Labeling**: Automatically marks issues that might be affected by external widgets not loading

### Global Summary Statistics
- **Heuristic Distribution**: Bar plot showing count of issues per heuristic (1-10)
- **Severity Distribution**: Bar plot showing count of issues per severity level (Cosmetic, Minor, Major, Critical)
- **Overall Score**: Displays calculated overall score for the page
- **Issue Count**: Shows total issues found (with filtering applied)

### Analysis Data Loading
- Dynamically loads desktop and mobile analysis JSON files
- Handles loading states and error cases
- Supports both desktop and mobile overlay images

---

## 4. LLM Recommendations Page (`/llm-recommendations`)

**Purpose**: Documentation of LLM-based recommendations for improving the autograder

**Key Features**:

### Comprehensive Recommendations
- **Multi-LLM Analysis**: Summarizes recommendations from ChatGPT, Claude, and Gemini
- **Unified Principles**: Presents overlapping recommendations as unified principles
- **Unique Perspectives**: Notes where different LLMs have differing views

### Key Recommendation Categories
1. **Temperature and Consistency**: Lower temperature for deterministic scoring
2. **Quantifiable Rules**: Replace subjective language with countable rules
3. **Prompt Length**: Reduce prompt length and instruction density
4. **Structured Scoring**: Use step-by-step scoring instructions
5. **JSON Schema**: Separate JSON schema from instructional text
6. **JSON Output Constraints**: Enforce strict zero-tolerance JSON output constraints
7. **Comment Field Guidelines**: Enforce strict comment field guidelines
8. **Token Limits**: Optimize token limits to prevent truncation
9. **Few-Shot Examples**: Include few-shot examples for critical criteria
10. **Error Handling**: Strengthen JSON parsing and error handling

### Implementation Status
- Shows which recommendations have been applied to the current system
- Includes original prompt code reference that was analyzed by LLMs
- Documents the evolution of the autograder design based on LLM feedback

---

## Technical Implementation Notes

### Backend (FastAPI)
- **PDF Processing**: Uses `pdfplumber` for text extraction and page rendering
- **LLM Integration**: Google Gemini 2.5 Flash API for analysis
- **Robust JSON Parsing**: Multiple fallback methods for handling incomplete or malformed JSON responses
- **Error Handling**: Comprehensive error handling with partial data extraction
- **Analysis Storage**: Saves individual page analysis results to JSON files

### Frontend (React + TypeScript)
- **Real-Time Updates**: Uses React state management for live progress tracking
- **Responsive Design**: Tailwind CSS for modern, responsive UI
- **Type Safety**: Full TypeScript implementation with proper type definitions
- **Data Visualization**: Bar plots for heuristic and severity distributions
- **Image Handling**: Base64 image encoding for PDF page display

### Data Flow
1. PDF uploaded → Backend extracts pages → Frontend displays pages
2. User clicks "Analyze with Gemini" → Backend processes pages concurrently → Frontend updates in real-time
3. Analysis complete → Frontend calculates summary scores → Displays final report
4. Optional: User enables comparison → Frontend loads Julian site data → Compares and displays matches

---

## Summary

The autograder system provides a comprehensive solution for automated grading of heuristic evaluation assignments. It combines:
- **Intelligent Analysis**: LLM-powered page classification and violation extraction
- **Structured Scoring**: Detailed rubric-based evaluation across 8 core criteria plus bonus points
- **Reference Comparison**: Ability to compare student work against expert analysis
- **Visual Feedback**: Screenshot overlays and detailed issue annotations
- **Transparency**: Full documentation of LLM recommendations and system design decisions

The system is designed to provide consistent, fair, and detailed feedback to students while reducing grading workload for instructors.

