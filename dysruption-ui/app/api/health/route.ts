import { NextResponse } from 'next/server';

/**
 * Health check endpoint for Railway
 * Returns 200 immediately with no dependencies
 */
export async function GET() {
  return NextResponse.json(
    { 
      status: 'alive', 
      service: 'invariant-ui',
      timestamp: new Date().toISOString()
    },
    { status: 200 }
  );
}

export const runtime = 'nodejs';
