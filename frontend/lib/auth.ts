import { jwtDecode } from 'jwt-decode'

type AccessTokenClaims = {
  user_roles?: string[]
}

export function getRolesFromToken(accessToken: string): string[] {
  try {
    return jwtDecode<AccessTokenClaims>(accessToken).user_roles ?? []
  } catch {
    return []
  }
}
