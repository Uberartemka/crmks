export interface Sku {
  id: number
  sku: string
  category: string
  gost: string
  d: number | null
  D: number | null
  B: number | null
  type: string
  brand: string
  stock: string
  price: number
  img: string
}

export interface SkuInput {
  sku: string
  category?: string
  gost?: string
  d?: number | null
  D?: number | null
  B?: number | null
  type?: string
  brand?: string
  stock?: string
  price: number
  img?: string
}
