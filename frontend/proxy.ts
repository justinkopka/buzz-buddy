import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { getRolesFromToken } from '@/lib/auth'

export async function proxy(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const PUBLIC_ROUTES = ['/login', '/signup', '/forgot-password', '/update-password']

  const isPublicRoute = PUBLIC_ROUTES.some(route =>
    request.nextUrl.pathname.startsWith(route)
  )

  const isAdminRoute = request.nextUrl.pathname.startsWith('/admin')

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          )
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  if (!user && !isPublicRoute) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  if (isAdminRoute) {
    const { data: { session } } = await supabase.auth.getSession()
    const roles = session ? getRolesFromToken(session.access_token) : []
    if (!roles.includes('admin')) {
      const url = request.nextUrl.clone()
      url.pathname = '/'
      return NextResponse.redirect(url)
    }
  }

  return supabaseResponse
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|auth).*)'],
}
