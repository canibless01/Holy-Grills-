/**
 * Upload contract — POST /api/upload/signature (uploads.py).
 * Step 1 of the image flow; step 2 is a direct browser upload to Cloudinary
 * using the returned signature (see components/admin/ImageUploader.jsx).
 */
export interface UploadSignatureRequest {
  folder?: string;
  [key: string]: unknown;
}

export interface UploadSignatureResponse {
  signature: string;
  timestamp: number;
  api_key: string;
  cloud_name: string;
  folder?: string;
  [key: string]: unknown;
}
