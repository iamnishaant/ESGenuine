import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface ClaimInput {
  id: string;
  text: string;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { claims, companyName, sector } = await req.json();
    
    if (!claims || !Array.isArray(claims) || claims.length === 0) {
      return new Response(
        JSON.stringify({ error: 'At least one claim is required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const LOVABLE_API_KEY = Deno.env.get('LOVABLE_API_KEY');
    if (!LOVABLE_API_KEY) {
      console.error('LOVABLE_API_KEY is not configured');
      throw new Error('AI service not configured');
    }

    console.log(`Analyzing ${claims.length} claims for:`, companyName, 'in sector:', sector);

    const claimsList = claims.map((c: ClaimInput, i: number) => `[Claim ${i + 1} - ID: ${c.id}]: "${c.text}"`).join('\n\n');

    const systemPrompt = `You are an ESG (Environmental, Social, Governance) claim analysis expert for the PHAROS-INTEGRITY platform. You analyze multiple corporate sustainability claims and identify relationships between them.

For EACH claim, analyze:
1. **Claim Type**: Categorize (Carbon Emissions, Renewable Energy, Water Conservation, Biodiversity, Supply Chain, Social Impact, Governance)
2. **Specificity Score** (1-10): How specific and measurable?
3. **Verifiability Score** (1-10): Can be verified with data?
4. **Key Metrics**: Quantifiable targets mentioned
5. **Red Flags**: Greenwashing indicators or vague language
6. **Risk Level**: Low, Medium, or High

For the OVERALL REPORT, analyze claim relationships:
- **Contradictions**: Claims that conflict with each other (e.g., "100% renewable by 2025" vs "expanding coal operations")
- **Supporting**: Claims that reinforce each other
- **Duplicates**: Claims making essentially the same point
- **Inconsistencies**: Timeline or scope mismatches

Be concise and actionable. Focus on cross-claim analysis.`;

    const userPrompt = `Analyze these ESG claims from ${companyName || 'Unknown Company'} (${sector || 'Unknown Sector'}):

${claimsList}

Provide analysis in this JSON format:
{
  "claims": [
    {
      "id": "claim_id_here",
      "claimType": "string",
      "specificityScore": number,
      "verifiabilityScore": number,
      "keyMetrics": ["string"],
      "redFlags": ["string"],
      "riskLevel": "Low" | "Medium" | "High",
      "summary": "string (1-2 sentences)"
    }
  ],
  "relationships": {
    "contradictions": [
      {
        "claimIds": ["id1", "id2"],
        "description": "Why these claims contradict",
        "severity": "High" | "Medium" | "Low"
      }
    ],
    "supporting": [
      {
        "claimIds": ["id1", "id2"],
        "description": "How these claims support each other"
      }
    ],
    "duplicates": [
      {
        "claimIds": ["id1", "id2"],
        "description": "Why these are essentially duplicates"
      }
    ],
    "inconsistencies": [
      {
        "claimIds": ["id1", "id2"],
        "description": "Timeline or scope mismatches"
      }
    ]
  },
  "overallRiskLevel": "Low" | "Medium" | "High",
  "reportSummary": "string (2-3 sentences summarizing the overall claim landscape)"
}`;

    const response = await fetch('https://ai.gateway.lovable.dev/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${LOVABLE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'google/gemini-3-flash-preview',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('AI Gateway error:', response.status, errorText);
      
      if (response.status === 429) {
        return new Response(
          JSON.stringify({ error: 'Rate limit exceeded. Please try again later.' }),
          { status: 429, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
      if (response.status === 402) {
        return new Response(
          JSON.stringify({ error: 'AI credits depleted. Please add funds.' }),
          { status: 402, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
      
      throw new Error('Failed to analyze claims');
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;
    
    console.log('AI response received, length:', content?.length);

    let analysis;
    try {
      const jsonMatch = content.match(/```json\n?([\s\S]*?)\n?```/) || content.match(/\{[\s\S]*\}/);
      const jsonStr = jsonMatch ? (jsonMatch[1] || jsonMatch[0]) : content;
      analysis = JSON.parse(jsonStr);
    } catch (parseError) {
      console.error('Failed to parse AI response as JSON:', parseError);
      analysis = {
        claims: claims.map((c: ClaimInput) => ({
          id: c.id,
          claimType: 'Unknown',
          specificityScore: 5,
          verifiabilityScore: 5,
          keyMetrics: [],
          redFlags: ['Unable to fully parse claim'],
          riskLevel: 'Medium',
          summary: 'Analysis could not be completed.'
        })),
        relationships: {
          contradictions: [],
          supporting: [],
          duplicates: [],
          inconsistencies: []
        },
        overallRiskLevel: 'Medium',
        reportSummary: 'Analysis could not be fully completed. Manual review recommended.'
      };
    }

    return new Response(
      JSON.stringify({ analysis }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Error in analyze-claims function:', error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
