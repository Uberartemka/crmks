export interface StoredFile {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  is_image: boolean
  url: string
  thumbnail_url: string | null
}
